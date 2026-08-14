# main.py
import logging
import os
import uuid
from datetime import datetime
from typing import List, Optional, Iterator
from urllib.parse import urlparse

import aiofiles
import csv
from io import StringIO

from fastapi import FastAPI, Depends, HTTPException, status, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, EmailStr, validator
from pydantic_settings import BaseSettings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool

import models  # application models / ORM

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

try:
    engine_kwargs = {
        "echo": False,
        "pool_pre_ping": True,
    }

    parsed = urlparse(DATABASE_URL or "")
    scheme = parsed.scheme or ""

    if scheme.startswith("postgres") or "postgresql" in DATABASE_URL:
        # Cloud Run / serverless: do not use connection pooling
        engine_kwargs["poolclass"] = NullPool
        # Some DB drivers accept connect_args, others don't; keep conservative
        engine_kwargs["connect_args"] = {"connect_timeout": DB_CONNECT_TIMEOUT}
    else:
        # SQLite specific
        engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": DB_CONNECT_TIMEOUT}

    engine = create_engine(DATABASE_URL, **engine_kwargs)
    # quick connection test
    with engine.connect() as conn:
        logger.info("Database connection test successful")

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    logger.info("Database session factory created")

except Exception as e:
    logger.error(f"Database initialization error: {e}")
    logger.warning("App will start but database operations will fail until database is available")
    engine = None
    SessionLocal = None


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
    except Exception as e:
        logger.error(f"Database session error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


# ---------- Utility: CSV streaming generator ----------
def csv_row_generator(rows: List[models.NotarialSession]) -> Iterator[str]:
    """
    Yield CSV data in chunks to avoid holding large files in memory.
    Accepts a list of sessions (already fetched). We create rows for each act.
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
        signers = ", ".join([f"{c.first_name} {c.last_name}" for c in getattr(s, "clients", [])])
        for act in getattr(s, "acts", []):
            writer.writerow(
                [
                    s.session_date.strftime("%Y-%m-%d %H:%M:%S") if getattr(s, "session_date", None) else "",
                    signers,
                    getattr(s, "location_type", "") or "",
                    getattr(s, "ron_platform", "") or "N/A (In-Person)",
                    getattr(act, "document", None).document_title if getattr(act, "document", None) else "",
                    getattr(act, "act_type").value if getattr(act, "act_type", None) else "",
                    float(getattr(act, "statutory_fee", 0.0) or 0.0),
                    float(getattr(act, "additional_fee", 0.0) or 0.0),
                    getattr(s, "payment_status").value if getattr(s, "payment_status", None) else "",
                    getattr(s, "tamper_evident_seal_id", "") or "N/A",
                ]
            )
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)


# ---------- Endpoints ----------
@app.get("/api/journal/export")
def export_state_audit_ledger(
    start_date: Optional[str] = Query(None, description="Format: YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="Format: YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """
    Export notarial sessions to CSV. Streams the CSV so large datasets don't consume memory.
    """
    query = db.query(models.NotarialSession)

    try:
        if start_date:
            query = query.filter(models.NotarialSession.session_date >= datetime.strptime(start_date, "%Y-%m-%d"))
        if end_date:
            query = query.filter(models.NotarialSession.session_date <= datetime.strptime(end_date, "%Y-%m-%d"))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format; use YYYY-MM-DD")

    sessions = query.order_by(models.NotarialSession.session_date.asc()).all()

    filename = f"notarial_journal_export_{datetime.now().strftime('%Y%m%d')}.csv"
    generator = csv_row_generator(sessions)
    response = StreamingResponse(generator, media_type="text/csv")
    response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


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
    except Exception as e:
        logger.error(f"Error saving uploaded file: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save file")

    return {"file_path_hash": secure_hash_name, "original_name": file.filename}


@app.get("/api/documents/view/{file_hash}")
def get_document_preview(file_hash: str):
    file_path = os.path.join(UPLOAD_DIR, file_hash)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    # Let the server or reverse proxy determine content-type if unknown.
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
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        # Do not raise here to allow health endpoints to remain available


@app.on_event("shutdown")
def shutdown():
    """Dispose DB engine on shutdown."""
    try:
        if engine:
            engine.dispose()
            logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")


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
    act_type: models.ActType
    statutory_fee: float = 0.0
    additional_fee: float = 0.0
    notes: Optional[str] = None


class SessionCreate(BaseModel):
    notary_id: str
    client_ids: List[str]
    location_type: str
    meeting_address: Optional[str] = None
    notes: Optional[str] = None
    payment_status: models.PaymentStatus = models.PaymentStatus.unpaid
    payment_method: Optional[models.PaymentMethod] = None
    acts: List[ActCreate]


class SessionResponse(BaseModel):
    session_id: str
    date: datetime
    location_type: str
    total_fee: float
    payment_status: models.PaymentStatus
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
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating client: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create client.")


@app.get("/api/clients", response_model=List[ClientResponse])
def get_clients(db: Session = Depends(get_db)):
    """Retrieve all clients."""
    try:
        clients = db.query(models.Client).all()
        logger.info(f"Retrieved {len(clients)} clients")
        return clients
    except Exception as e:
        logger.error(f"Error fetching clients: {e}")
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
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating session: {e}")
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
                    "payment_status": s.payment_status,
                    "clients": [{"id": c.client_id, "name": f"{c.first_name} {c.last_name}"} for c in getattr(s, "clients", [])],
                    "acts_count": len(getattr(s, "acts", [])),
                }
            )

        logger.info(f"Retrieved {len(sessions)} sessions")
        return output
    except Exception as e:
        logger.error(f"Error fetching sessions: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve sessions.")
