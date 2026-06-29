"""
Database engine, session, and ORM models for the Village Portal.
Uses SQLAlchemy 2.0 style with SQLite by default (swap DATABASE_URL for Postgres in production).
"""
import os
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./village_portal.db")

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ===== MODELS =====

class Admin(Base):
    __tablename__ = "admin"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    password_hash = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Service(Base):
    __tablename__ = "service"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    contact = Column(String(50), nullable=True)
    is_emergency = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Event(Base):
    __tablename__ = "event"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    date = Column(String(50), nullable=False)
    location = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Announcement(Base):
    __tablename__ = "announcement"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    date = Column(String(50), nullable=False)
    is_important = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Complaint(Base):
    __tablename__ = "complaint"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    location = Column(String(200), nullable=True)
    status = Column(String(50), default="Pending")
    date = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def get_db():
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
