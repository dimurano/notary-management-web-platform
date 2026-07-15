import logging
import os
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

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
    "sqlite:///./notary_journal.db"
)
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://localhost:8000"
).split(",")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

logger.info(f"Starting Notary API in {ENVIRONMENT} mode")

# Database setup
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Notary Public Journal API", version="1.0.0")

# CORS middleware with restricted origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in ALLOWED_ORIGINS],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "Authorization"],
)

# Dependency to get db session
def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database session error: {e}")
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

@app.get("/api/health")
def health_check():
    """Health check endpoint for deployment monitoring."""
    return {"status": "ok", "service": "Notary Public Journal API"}
