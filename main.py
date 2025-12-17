import json
import os
import requests
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from pypdf import PdfReader
from docx import Document


# SQLite database file
SQLALCHEMY_DATABASE_URL = "sqlite:///./notes.db"

# Create the engine (connection to the database)
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},  # needed for SQLite with FastAPI
)

# Create a database session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for ORM models
Base = declarative_base()


# -----------------------
# ORM model (database table)
# -----------------------

class Note(Base):
    __tablename__ = "notes"  # table name in the database

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    content = Column(String)


# Create the tables
Base.metadata.create_all(bind=engine)

# Pydantic schemas
class NoteCreate(BaseModel):
    title: str
    content: str


class NoteUpdate(BaseModel):
    title: str | None = None
    content: str | None = None


class NoteOut(BaseModel):
    id: int
    title: str
    content: str

    class Config:
        orm_mode = True  

class NoteSummary(BaseModel):
    id: int
    title: str
    content: str
    summary: str


# FastAPI app & DB dependency
app = FastAPI(title="Notes API")


#    Dependency that provides a database session to path operations.
#    It opens a session at the start of the request and closes it at the end.
def get_db() -> Session:

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# CRUD ENDPOINTS

# CREATE a note
@app.post("/notes", response_model=NoteOut)
def create_note(note: NoteCreate, db: Session = Depends(get_db)):
    db_note = Note(title=note.title, content=note.content)
    db.add(db_note)
    db.commit()
    db.refresh(db_note)
    return db_note


# READ all notes
@app.get("/notes", response_model=list[NoteOut])
def read_notes(db: Session = Depends(get_db)):
    notes = db.query(Note).all()
    return notes


# READ one note by ID
@app.get("/notes/{note_id}", response_model=NoteOut)
def read_note(note_id: int, db: Session = Depends(get_db)):
    note = db.query(Note).filter(Note.id == note_id).first()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


# UPDATE a note
@app.put("/notes/{note_id}", response_model=NoteOut)
def update_note(note_id: int, note_data: NoteUpdate, db: Session = Depends(get_db)):
    note = db.query(Note).filter(Note.id == note_id).first()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")

    # Only update fields that are provided (not None)
    if note_data.title is not None:
        note.title = note_data.title
    if note_data.content is not None:
        note.content = note_data.content

    db.commit()
    db.refresh(note)
    return note


# DELETE a note
@app.delete("/notes/{note_id}")
def delete_note(note_id: int, db: Session = Depends(get_db)):
    note = db.query(Note).filter(Note.id == note_id).first()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")

    db.delete(note)
    db.commit()
    return {"detail": "Note deleted"}

# SUMMARIZE a note using Ollama
@app.post("/notes/{note_id}/summarize", response_model=NoteSummary)
def summarize_note(note_id: int, db: Session = Depends(get_db)):
    # 1. Get the note from the database
    note = db.query(Note).filter(Note.id == note_id).first()
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")

    # 2. Build a prompt for Ollama
    prompt = f"""
    Please summarize the following note in 3–5 clear bullet points.
    Focus on the main ideas and keep the language simple.

    Note content:
    {note.content}
    """

    # 3. Call Ollama's local API
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3",  
                "prompt": prompt,
                "stream": False      
            },
            timeout=60,
        )
    except requests.exceptions.RequestException as e:
        # Network / connection error
        raise HTTPException(
            status_code=500,
            detail=f"Error connecting to Ollama: {e}"
        )

    if response.status_code != 200:
        # Ollama returned an error
        raise HTTPException(
            status_code=500,
            detail=f"Ollama error: {response.text}"
        )

    data = response.json()
    summary_text = data.get("response", "").strip()

    if not summary_text:
        raise HTTPException(
            status_code=500,
            detail="No summary returned from Ollama."
        )

    # 4. Return original note + summary
    return NoteSummary(
        id=note.id,
        title=note.title,
        content=note.content,
        summary=summary_text,
    )
