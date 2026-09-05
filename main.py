import sys
import logging
import os
import re
import uuid
import aiofiles
import csv

import models  # application models / ORM

from datetime import datetime, date, time
from typing import List, Optional, Iterator
from urllib.parse import urlparse
from io import StringIO
from contextlib import asynccontextmanager  # Required for modern lifespan handlers
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
     @app.get("/")
     async def read_root(): 
     return FileResponse("index.html") 

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator, validator
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------- Settings (centralized & validated - Pydantic v2 Style) ----------
class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/notary_journal.db"
    allowed_origins: Optional[str] = "http://localhost:3000"
    environment: str = "development"
    upload_dir: str = "./secure_vault"
    db_connect_timeout: int = 1

    # 1. Replaced 'class Config' with the modern 'model_config' dictionary
    model_config = ConfigDict(
        env_file=".env",
        env_file_encoding="utf-8"
    )

    # 2. Replaced '@validator(..., pre=True)' with '@field_validator(..., mode="before")'
    @field_validator("allowed_origins", mode="before")
    @classmethod
    def split_allowed_origins(cls, v: Optional[str]) -> str:
        if v is None:
            return ""
        if isinstance(v, list):
            return ",".join(v)
        return v

settings = Settings()

def mask_database_url(url: Optional[str]) -> str:
    if not url:
        return "not-set"
    try:
        p = urlparse(url)
        if p.scheme in ("sqlite",) and p.path:
            path = p.path
            if len(path) > 20:
                return f"{p.scheme}://{path[:20]}..."
            return f"{p.scheme}://{path}"
        if p.username or p.password:
            host = p.hostname or "localhost"
            port = f":{p.port}" if p.port else ""
            return f"{p.scheme}://{host}{port}/****"
        return url if len(url) <= 80 else url[:80] + "..."
    except Exception:
        return "malformed"

DATABASE_URL = settings.database_url
ALLOWED_ORIGINS = [o.strip() for o in (settings.allowed_origins or "").split(",") if o.strip()]
ENVIRONMENT = settings.environment
UPLOAD_DIR = settings.upload_dir
DB_CONNECT_TIMEOUT = settings.db_connect_timeout

# ----------Move initialization variables to a global scope so endpoints can access them----------
engine = None
SessionLocal = None


def init_engine(database_url: Optional[str]):
    if not database_url:
        logger.warning("DATABASE_URL not set; database disabled")
        return None, None

    engine_kwargs = {"echo": False, "pool_pre_ping": True}
    parsed = urlparse(database_url or "")
    scheme = (parsed.scheme or "").lower()

    if scheme.startswith("postgres") or scheme.startswith("postgresql"):
        engine_kwargs["poolclass"] = NullPool

    if scheme in ("sqlite", "sqlite3"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        if DB_CONNECT_TIMEOUT:
            engine_kwargs.setdefault("connect_args", {})["connect_timeout"] = DB_CONNECT_TIMEOUT

    try:
        eng = create_engine(database_url, **engine_kwargs)
        with eng.connect() as conn:
            logger.info("Database connection test successful")
        SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=eng)
        logger.info("Database session factory created")
        return eng, SessionFactory
    except Exception:
        logger.exception("Database initialization error")
        return None, None


# ---------- Lifespan Management ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles initialization and cleanup strategies for the application instance.
    Replaces deprecated app.on_event mechanics.
    """
    global engine, SessionLocal
    
    # --- STARTUP LOGIC ---
    logger.info(f"Starting Notary API in {ENVIRONMENT} mode")
    logger.info(f"Database URL: {mask_database_url(DATABASE_URL)}")
    logger.info(f"Allowed origins: {ALLOWED_ORIGINS or ['<none configured>']}")
    
    # Ensure local directory paths are mapped
    db_dir = "./data" 
    if not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    # Initialize connection structures
    engine, SessionLocal = init_engine(DATABASE_URL)
    
    yield  # Application is live and serving requests
    
    # --- SHUTDOWN LOGIC ---
    if engine:
        logger.info("Disposing database engine connections...")
        engine.dispose()
    logger.info("Notary API shutdown sequence completed")


# ---------- FastAPI App Instance ----------
app = FastAPI(
    title="Notary Public Journal API", 
    version="1.0.0",
    lifespan=lifespan  # Attach your lifespan definition here

    
)

# ----------CORS middleware----------
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or [],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


# ---------- Dependency ----------
def get_db() -> Iterator[Session]:
    if SessionLocal is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available",
        )
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Database session error; rolled back")
        raise
    finally:
        db.close()


# ---------- Utility: CSV streaming generator ----------

def csv_row_generator(rows: Iterator[models.NotarialSession]) -> Iterator[str]:
    """
    Yield CSV data in chunks to avoid holding large files in memory.
    Accepts an iterable/query that yields NotarialSession instances lazily.
    """
    buffer = StringIO()
    writer = csv.writer(buffer)

    # header
    writer.writerow(
        [
            "Transaction Date",
            "Signer Name(s)",
            "Location / Medium",
            "Platform (RON)",
            "Document Title",
            "Act Type",
            "Statutory Fee",
            "Additional Fee",
            "Payment Status",
            "Seal Reference ID",
        ]
    )
    yield buffer.getvalue()
    buffer.seek(0)
    buffer.truncate(0)

    for s in rows:
        try:
            signers = []
            for c in getattr(s, "clients", []) or []:
                first = getattr(c, "first_name", "") or ""
                last = getattr(c, "last_name", "") or ""
                name = (first + " " + last).strip()
                if name:
                    signers.append(name)
            signer_str = ", ".join(signers)

            session_date = getattr(s, "session_date", None)
            date_str = session_date.strftime("%Y-%m-%d %H:%M:%S") if session_date else ""

            acts = getattr(s, "acts", []) or [None]
            for act in acts:
                if act is None:
                    document_title = ""
                    act_type = ""
                    statutory_fee = ""
                    additional_fee = ""
                else:
                    doc = getattr(act, "document", None)
                    document_title = getattr(doc, "document_title", "") if doc is not None else ""
                    act_type_attr = getattr(act, "act_type", None)
                    act_type = getattr(act_type_attr, "value", str(act_type_attr)) if act_type_attr is not None else ""
                    statutory_fee = str(getattr(act, "statutory_fee", ""))
                    additional_fee = str(getattr(act, "additional_fee", ""))

                row = [
                    date_str,
                    signer_str,
                    getattr(s, "location_type", "") or "",
                    getattr(s, "ron_platform", "") or "",
                    document_title,
                    act_type,
                    statutory_fee,
                    additional_fee,
                    getattr(s, "payment_status", "") and getattr(getattr(s, "payment_status", None), "value", str(getattr(s, "payment_status", ""))) or "",
                    getattr(s, "tamper_evident_seal_id", "") or "",
                ]

                writer.writerow(row)
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate(0)
        except Exception:
            logger.exception("Error while rendering CSV row")
            raise
