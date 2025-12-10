from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session


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
