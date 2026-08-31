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
from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, EmailStr, @field_validator, validator
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

# Extract directory from database path or hardcode it
db_dir = "./data" 
if not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------- Settings (centralized & validated) ----------
class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/notary_journal.db"
    allowed_origins: Optional[str] = "http://localhost:3000"
    environment: str = "development"
    upload_dir: str = "./secure_vault"
    db_connect_timeout: int = 1

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @validator("allowed_origins", pre=True)
    def split_allowed_origins(cls, v: Optional[str]) -> str:
        # Keep as a comma-separated string in settings; we'll split when creating the app
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
            # hide full filesystem path for sqlite
            path = p.path
            if len(path) > 20:
                return f"{p.scheme}://{path[:20]}..."
            return f"{p.scheme}://{path}"
        if p.username or p.password:
            host = p.hostname or "localhost"
            port = f":{p.port}" if p.port else ""
            return f"{p.scheme}://{host}{port}/****"
        # fallback -- trim if too long
        return url if len(url) <= 80 else url[:80] + "..."
    except Exception:
        return "malformed"


DATABASE_URL = settings.database_url
ALLOWED_ORIGINS = [o.strip() for o in (settings.allowed_origins or "").split(",") if o.strip()]
ENVIRONMENT = settings.environment
UPLOAD_DIR = settings.upload_dir
DB_CONNECT_TIMEOUT = settings.db_connect_timeout

logger.info(f"Starting Notary API in {ENVIRONMENT} mode")
logger.info(f"Database URL: {mask_database_url(DATABASE_URL)}")
logger.info(f"Allowed origins: {ALLOWED_ORIGINS or ['<none configured>']}")


# ---------- Database setup ----------
engine = None
SessionLocal = None


def init_engine(database_url: Optional[str]):
    if not database_url:
        logger.warning("DATABASE_URL not set; database disabled")
        return None, None

    engine_kwargs = {"echo": False, "pool_pre_ping": True}
    parsed = urlparse(database_url or "")
    scheme = (parsed.scheme or "").lower()

    # Cloud Run / serverless: do not use connection pooling for Postgres
    if scheme.startswith("postgres") or scheme.startswith("postgresql"):
        engine_kwargs["poolclass"] = NullPool

    # Some DB drivers accept connect_args, others don't; keep conservative
    if scheme in ("sqlite", "sqlite3"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    else:
        if DB_CONNECT_TIMEOUT:
            engine_kwargs.setdefault("connect_args", {})["connect_timeout"] = DB_CONNECT_TIMEOUT

    try:
        eng = create_engine(database_url, **engine_kwargs)
        # quick connection test
        with eng.connect() as conn:
            logger.info("Database connection test successful")
        SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=eng)
        logger.info("Database session factory created")
        return eng, SessionFactory
    except Exception:
        logger.exception("Database initialization error")
        return None, None


engine, SessionLocal = init_engine(DATABASE_URL)


# ---------- FastAPI app ----------
app = FastAPI(title="Notary Public Journal API", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or [],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Ensure upload directory exists
os.makedirs(UPLOAD_DIR, exist_ok=True)


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
            logger.exception("Error while rendering a CSV row for session id=%s", getattr(s, "session_id", "<unknown>"))
            continue


# ---------- Endpoints ----------
@app.get("/api/journal/export")
def export_state_audit_ledger(
    start_date: Optional[date] = Query(None, description="Format: YYYY-MM-DD"),
    end_date: Optional[date] = Query(None, description="Format: YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """
    Export notarial sessions to CSV. Streams the CSV so large datasets don't consume memory.
    """
    try:
        query = db.query(models.NotarialSession)

        if start_date:
            query = query.filter(models.NotarialSession.session_date >= datetime.combine(start_date, time.min))
        if end_date:
            query = query.filter(models.NotarialSession.session_date <= datetime.combine(end_date, time.max))

        # Use yield_per to avoid loading entire resultset into memory
        query = query.order_by(models.NotarialSession.session_date.asc()).yield_per(200).enable_eagerloads(False)

        filename = f"notarial_journal_export_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.csv"
        generator = csv_row_generator(query)
        response = StreamingResponse(generator, media_type="text/csv")
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response
    except HTTPException:
        raise
    except Exception:
        logger.exception("Failed to generate journal export")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to generate export")


@app.post("/api/documents/upload")
async def upload_notarial_document(file: UploadFile = File(...)):
    """
    Secure upload that writes to disk with an obfuscated filename.
    Uses chunked async writing to handle large files.
    """
    file_extension = os.path.splitext(file.filename)[1]
    secure_hash_name = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, secure_hash_name)

    try:
        # stream read / write in chunks
        async with aiofiles.open(file_path, "wb") as out_file:
            while True:
                chunk = await file.read(1024 * 64)
                if not chunk:
                    break
                await out_file.write(chunk)
    except Exception:
        logger.exception("Error saving uploaded file")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save file")

    return {"file_path_hash": secure_hash_name, "original_name": file.filename}


# Validate file identifiers (allow alnum, dash, underscore, dot; reasonable length)
FILE_HASH_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}(?:\.[A-Za-z0-9]+)?$")


@app.get("/api/documents/view/{file_hash}")
def get_document_preview(file_hash: str):
    # Validate format
    if not FILE_HASH_RE.match(file_hash):
        logger.warning("Invalid file identifier requested: %s", file_hash)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file identifier")

    upload_dir_abs = os.path.abspath(UPLOAD_DIR)
    file_path = os.path.abspath(os.path.join(upload_dir_abs, file_hash))

    # Ensure the resolved path is inside the upload directory
    if not file_path.startswith(upload_dir_abs + os.sep) and file_path != upload_dir_abs:
        logger.warning("Attempted path traversal or invalid file path: %s", file_path)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path")

    if not os.path.exists(file_path):
        logger.info("File not found: %s", file_path)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    return FileResponse(file_path)


# ---------- Startup / Shutdown ----------
@app.on_event("startup")
def startup():
    """Initialize database on startup (create tables if DB available)."""
    try:
        if engine is None:
            logger.warning("Database engine not initialized - skipping table creation")
            return
        logger.info("Creating database tables...")
        models.Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception:
        logger.exception("Error creating database tables on startup")


@app.on_event("shutdown")
def shutdown():
    """Dispose DB engine on shutdown."""
    try:
        if engine:
            engine.dispose()
            logger.info("Database connections closed")
    except Exception:
        logger.exception("Error during shutdown")


# ---------- Schemas ----------
class ClientCreate(BaseModel):
    first_name: str
    last_name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    street_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None


class ClientResponse(ClientCreate):
    client_id: str
    created_at: datetime


class DocumentCreate(BaseModel):
    document_title: str
    page_count: int = 1


class ActCreate(BaseModel):
    document: DocumentCreate
    act_type: str  # decoupled from ORM enum for API layer
    statutory_fee: float = 0.0
    additional_fee: float = 0.0
    notes: Optional[str] = None


class SessionCreate(BaseModel):
    notary_id: str
    client_ids: List[str]
    location_type: str
    meeting_address: Optional[str] = None
    notes: Optional[str] = None
    payment_status: Optional[str] = "unpaid"
    payment_method: Optional[str] = None
    acts: List[ActCreate]


class SessionResponse(BaseModel):
    session_id: str
    date: datetime
    location_type: str
    total_fee: float
    payment_status: Optional[str]
    clients: List[dict]
    acts_count: int


# ---------- Health & Root ----------
@app.get("/api/health")
def health_check():
    db_status = "connected" if engine else "unavailable"
    return {
        "status": "ok",
        "service": "Notary Public Journal API",
        "environment": ENVIRONMENT,
        "database": db_status,
    }


@app.get("/")
def root():
    return {
        "message": "Notary Public Journal API",
        "docs": "/docs",
        "health": "/api/health",
    }


# ---------- Client endpoints ----------
@app.post("/api/clients", status_code=status.HTTP_201_CREATED, response_model=ClientResponse)
def create_client(client: ClientCreate, db: Session = Depends(get_db)):
    """Create a new client record."""
    try:
        if client.email:
            existing = db.query(models.Client).filter(models.Client.email == client.email).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail="A client with this email already exists."
                )

        db_client = models.Client(**client.dict())
        db.add(db_client)
        db.commit()
        db.refresh(db_client)
        logger.info(f"Client created: {getattr(db_client, 'client_id', '<unknown>')}")
        return db_client
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        logger.exception("Error creating client")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create client.")


@app.get("/api/clients", response_model=List[ClientResponse])
def get_clients(db: Session = Depends(get_db)):
    """Retrieve all clients."""
    try:
        clients = db.query(models.Client).all()
        logger.info(f"Retrieved {len(clients)} clients")
        return clients
    except Exception:
        logger.exception("Error fetching clients")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve clients.")


# ---------- Journal / Session endpoints ----------
@app.post("/api/sessions", status_code=status.HTTP_201_CREATED)
def create_notarial_session(session_data: SessionCreate, db: Session = Depends(get_db)):
    """Create a new notarial session with associated documents and acts."""
    try:
        # 1. Verify notary exists
        notary = db.query(models.Notary).filter(models.Notary.notary_id == session_data.notary_id).first()
        if not notary:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notary not found.")

        # 2. Verify commission is not expired
        if getattr(notary, "commission_expires", None) and notary.commission_expires < datetime.now().date():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Notary commission has expired.")

        # 3. Verify clients exist
        clients = db.query(models.Client).filter(models.Client.client_id.in_(session_data.client_ids)).all()
        if len(clients) != len(session_data.client_ids):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="One or more client IDs are invalid.")

        # 4. Calculate totals from nested acts
        total_fee = sum((act.statutory_fee or 0.0) + (act.additional_fee or 0.0) for act in session_data.acts)

        # 5. Create Session instance
        db_session = models.NotarialSession(
            notary_id=session_data.notary_id,
            location_type=session_data.location_type,
            meeting_address=session_data.meeting_address,
            notes=session_data.notes,
            total_fee=total_fee,
            payment_status=session_data.payment_status,
            payment_method=session_data.payment_method,
        )

        # Attach clients via relationship
        db_session.clients = clients
        db.add(db_session)
        db.flush()  # ensure session id is available

        # 6. Handle nested documents and individual act entries
        for act_item in session_data.acts:
            db_doc = models.Document(document_title=act_item.document.document_title, page_count=act_item.document.page_count)
            db.add(db_doc)
            db.flush()

            db_act = models.ActDocument(
                session_id=db_session.session_id,
                document_id=db_doc.document_id,
                act_type=act_item.act_type,
                statutory_fee=act_item.statutory_fee,
                additional_fee=act_item.additional_fee,
                notes=act_item.notes,
            )
            db.add(db_act)

        db.commit()
        db.refresh(db_session)
        logger.info(f"Notarial session created: {getattr(db_session, 'session_id', '<unknown>')}")
        return {"message": "Session and journal entry recorded successfully", "session_id": db_session.session_id}
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        logger.exception("Error creating session")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create notarial session.")


@app.get("/api/sessions", response_model=List[SessionResponse])
def get_journal_ledger(db: Session = Depends(get_db)):
    """Retrieve all notarial sessions for the journal ledger."""
    try:
        sessions = db.query(models.NotarialSession).all()

        output = []
        for s in sessions:
            output.append(
                {
                    "session_id": s.session_id,
                    "date": s.session_date,
                    "location_type": s.location_type,
                    "total_fee": float(s.total_fee),
                    "payment_status": getattr(s, 'payment_status', None) and getattr(getattr(s, 'payment_status', None), 'value', str(getattr(s, 'payment_status', None))) or None,
                    "clients": [{"id": c.client_id, "name": f"{c.first_name} {c.last_name}"} for c in getattr(s, "clients", [])],
                    "acts_count": len(getattr(s, "acts", [])),
                }
            )

        logger.info(f"Retrieved {len(sessions)} sessions")
        return output
    except Exception:
        logger.exception("Error fetching sessions")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve sessions.")
