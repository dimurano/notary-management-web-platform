import logging
import os
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from fastapi import UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

import models

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Environment configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "sqlite:///./data/notary_journal.db"
)
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:8000"
).split(",")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

logger.info(f"Starting Notary API in {ENVIRONMENT} mode")
logger.info(f"Database URL: {DATABASE_URL[:50]}...")

# Database setup - with error handling for Cloud Run
engine = None
SessionLocal = None

try:
    # Use NullPool for Cloud Run to avoid connection pooling issues
    engine_kwargs = {
        "echo": False,
        "pool_pre_ping": True,
    }
    
    if "postgresql" in DATABASE_URL or "postgres" in DATABASE_URL:
        # PostgreSQL with Cloud SQL
        engine_kwargs["poolclass"] = NullPool  # Don't pool connections in Cloud Run
        engine_kwargs["connect_args"] = {"timeout": 10}
    else:
        # SQLite
        engine_kwargs["connect_args"] = {"check_same_thread": False, "timeout": 10}
    
    engine = create_engine(DATABASE_URL, **engine_kwargs)
    
    # Test connection without creating tables yet
    with engine.connect() as conn:
        logger.info("Database connection test successful")
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    logger.info("Database session factory created")
    
except Exception as e:
    logger.error(f"Database initialization error: {e}")
    logger.warning("App will start but database operations will fail until database is available")
    engine = None
    SessionLocal = None

# Create FastAPI app
app = FastAPI(title="Notary Public Journal API", version="1.0.0")

# Create FastAPI Secure File Endpoint

import csv
from io import StringIO
from fastapi.responses import StreamingResponse
from fastapi import Query

@app.get("/api/journal/export")
def export_state_audit_ledger(
    start_date: str = Query(None, description="Format: YYYY-MM-DD"),
    end_date: str = Query(None, description="Format: YYYY-MM-DD"),
    db: Session = Depends(get_db)
):
    query = db.query(models.NotarialSession)
    
    # Filter records dynamically based on user query choices
    if start_date:
        query = query.filter(models.NotarialSession.session_date >= datetime.strptime(start_date, "%Y-%m-%d"))
    if end_date:
        query = query.filter(models.NotarialSession.session_date <= datetime.strptime(end_date, "%Y-%m-%d"))
        
    sessions = query.order_by(models.NotarialSession.session_date.asc()).all()
    
    # Setup standard in-memory string stream buffer
    stream = StringIO()
    writer = csv.writer(stream)
    
    # Write structural state ledger compliance header rows
    writer.writerow([
        "Transaction Date", "Signer Name(s)", "Location / Medium", 
        "Platform (RON)", "Document Title", "Act Type", 
        "Statutory Fee", "Additional Fee", "Payment Status", "Seal Reference ID"
    ])
    
    for s in sessions:
        signers = ", ".join([f"{c.first_name} {c.last_name}" for c in s.clients])
        
        # Unpack individual document entries nested inside this appointment block
        for act in s.acts:
            writer.writerow([
                s.session_date.strftime("%Y-%m-%d %H:%M:%S"),
                signers,
                s.location_type,
                s.ron_platform or "N/A (In-Person)",
                act.document.document_title,
                act.act_type.value,
                float(act.statutory_fee),
                float(act.additional_fee),
                s.payment_status.value,
                s.tamper_evident_seal_id or "N/A"
            ])
            
    # Reset stream pointer position
    stream.seek(0)
    
    response = StreamingResponse(iter([stream.getvalue()]), media_type="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename=notarial_journal_export_{datetime.now().strftime('%Y%m%d')}.csv"
    return responseUPLOAD_DIR = "./secure_vault"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/api/documents/upload")
async def upload_notarial_document(file: UploadFile = File(...)):
    # Create an obfuscated, unique file filename to decouple data leaks
    file_extension = os.path.splitext(file.filename)[1]
    secure_hash_name = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, secure_hash_name)
    
    # Streams file data onto local drive disk blocks safely
    with open(file_path, "wb") as buffer:
        content = await file.read()
        buffer.write(content)
        
    return {"file_path_hash": secure_hash_name, "original_name": file.filename}

@app.get("/api/documents/view/{file_hash}")
def get_document_preview(file_hash: str):
    file_path = os.path.join(UPLOAD_DIR, file_hash)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File details not found")
    return FileResponse(file_path, media_type="application/pdf")

# CORS middleware with restricted origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in ALLOWED_ORIGINS],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

# Startup event to create tables and initialize database
@app.on_event("startup")
def startup():
    """Initialize database on startup."""
    try:
        if engine is None:
            logger.warning("Database engine not initialized - skipping table creation")
            return
        
        logger.info("Creating database tables...")
        models.Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Error creating database tables: {e}")
        # Don't fail startup - let the app start and fail on actual database operations

@app.on_event("shutdown")
def shutdown():
    """Clean up database connections on shutdown."""
    try:
        if engine:
            engine.dispose()
            logger.info("Database connections closed")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

# Dependency to get db session
def get_db():
    if SessionLocal is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not available"
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

# Pydantic Schemas for Validation
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

# --- HEALTH & INFO ENDPOINTS ---

@app.get("/api/health")
def health_check():
    """Health check endpoint for deployment monitoring."""
    db_status = "connected" if engine else "unavailable"
    return {
        "status": "ok",
        "service": "Notary Public Journal API",
        "environment": ENVIRONMENT,
        "database": db_status
    }

@app.get("/")
def root():
    """Root endpoint - API documentation available at /docs"""
    return {
        "message": "Notary Public Journal API",
        "docs": "/docs",
        "health": "/api/health"
    }

# --- CLIENT ENDPOINTS ---

@app.post("/api/clients", status_code=status.HTTP_201_CREATED, response_model=ClientResponse)
def create_client(client: ClientCreate, db: Session = Depends(get_db)):
    """Create a new client record."""
    try:
        # Check for duplicate email if provided
        if client.email:
            existing = db.query(models.Client).filter(
                models.Client.email == client.email
            ).first()
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="A client with this email already exists."
                )
        
        db_client = models.Client(**client.model_dump())
        db.add(db_client)
        db.commit()
        db.refresh(db_client)
        logger.info(f"Client created: {db_client.client_id}")
        return db_client
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating client: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create client."
        )

@app.get("/api/clients", response_model=List[ClientResponse])
def get_clients(db: Session = Depends(get_db)):
    """Retrieve all clients."""
    try:
        clients = db.query(models.Client).all()
        logger.info(f"Retrieved {len(clients)} clients")
        return clients
    except Exception as e:
        logger.error(f"Error fetching clients: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve clients."
        )

# --- JOURNAL / SESSION ENDPOINTS ---

@app.post("/api/sessions", status_code=status.HTTP_201_CREATED)
def create_notarial_session(session_data: SessionCreate, db: Session = Depends(get_db)):
    """Create a new notarial session with associated documents and acts."""
    try:
        # 1. Verify notary exists
        notary = db.query(models.Notary).filter(
            models.Notary.notary_id == session_data.notary_id
        ).first()
        if not notary:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notary not found."
            )
        
        # 2. Verify commission is not expired
        if notary.commission_expires < datetime.now().date():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Notary commission has expired."
            )
        
        # 3. Verify clients exist
        clients = db.query(models.Client).filter(
            models.Client.client_id.in_(session_data.client_ids)
        ).all()
        if len(clients) != len(session_data.client_ids):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="One or more client IDs are invalid."
            )
        
        # 4. Calculate totals from nested acts
        total_fee = sum(
            act.statutory_fee + act.additional_fee 
            for act in session_data.acts
        )
        
        # 5. Create Session instance
        db_session = models.NotarialSession(
            notary_id=session_data.notary_id,
            location_type=session_data.location_type,
            meeting_address=session_data.meeting_address,
            notes=session_data.notes,
            total_fee=total_fee,
            payment_status=session_data.payment_status,
            payment_method=session_data.payment_method
        )
        
        # Attach clients via junction link
        db_session.clients = clients
        db.add(db_session)
        db.flush()  # Secure the session ID
        
        # 6. Handle nested documents and individual act entries
        for act_item in session_data.acts:
            db_doc = models.Document(
                document_title=act_item.document.document_title,
                page_count=act_item.document.page_count
            )
            db.add(db_doc)
            db.flush()
            
            db_act = models.ActDocument(
                session_id=db_session.session_id,
                document_id=db_doc.document_id,
                act_type=act_item.act_type,
                statutory_fee=act_item.statutory_fee,
                additional_fee=act_item.additional_fee,
                notes=act_item.notes
            )
            db.add(db_act)
        
        db.commit()
        db.refresh(db_session)
        logger.info(f"Notarial session created: {db_session.session_id}")
        return {
            "message": "Session and journal entry recorded successfully",
            "session_id": db_session.session_id
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create notarial session."
        )

@app.get("/api/sessions", response_model=List[SessionResponse])
def get_journal_ledger(db: Session = Depends(get_db)):
    """Retrieve all notarial sessions for the journal ledger."""
    try:
        sessions = db.query(models.NotarialSession).all()
        
        output = []
        for s in sessions:
            output.append({
                "session_id": s.session_id,
                "date": s.session_date,
                "location_type": s.location_type,
                "total_fee": float(s.total_fee),
                "payment_status": s.payment_status,
                "clients": [
                    {"id": c.client_id, "name": f"{c.first_name} {c.last_name}"}
                    for c in s.clients
                ],
                "acts_count": len(s.acts)
            })
        
        logger.info(f"Retrieved {len(sessions)} sessions")
        return output
    except Exception as e:
        logger.error(f"Error fetching sessions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve sessions."
        )
