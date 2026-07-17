{\rtf1\ansi\ansicpg1252\cocoartf2870
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0

\f0\fs24 \cf0 from fastapi import FastAPI, Depends, HTTPException, status\
from fastapi.middleware.cors import CORSMiddleware\
from pydantic import BaseModel, EmailStr\
from typing import List, Optional\
from datetime import date, datetime\
from sqlalchemy.orm import Session\
from sqlalchemy import create_engine\
from sqlalchemy.orm import sessionmaker\
import models\
\
# uwsgi: pip install pyuwsgi
uwsgi --http :$PORT -s /tmp/app.sock --manage-script-name --mount /app=main:app

# uvicorn: pip install uvicorn
uvicorn --port $PORT --host 0.0.0.0 main:app

# waitress: pip install waitress
waitress-serve --port $PORT main:app
\
# Database setup (SQLite for easy development, switch to PostgreSQL URL later)\
SQLALCHEMY_DATABASE_URL = "sqlite:///./notary_journal.db"\
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=\{"check_same_thread": False\})\
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)\
models.Base.metadata.create_all(bind=engine)\
\
app = FastAPI(title="Notary Public Journal API")\
\
# Enable CORS for frontend HTML access\
app.add_middleware(\
    CORSMiddleware,\
    allow_origins=["*"], # In production, replace with your exact frontend URL\
    allow_credentials=True,\
    allow_methods=["*"],\
    allow_headers=["*"],\
)\
\
# Dependency to get db session\
def get_db():\
    db = SessionLocal()\
    try:\
        yield db\
    finally:\
        db.close()\
\
# Pydantic Schemas for Validation\
class ClientCreate(BaseModel):\
    first_name: str\
    last_name: str\
    email: Optional[EmailStr] = None\
    phone: Optional[str] = None\
    street_address: Optional[str] = None\
    city: Optional[str] = None\
    state: Optional[str] = None\
    zip_code: Optional[str] = None\
\
class DocumentCreate(BaseModel):\
    document_title: str\
    page_count: int = 1\
\
class ActCreate(BaseModel):\
    document: DocumentCreate\
    act_type: models.ActType\
    statutory_fee: float = 0.0\
    additional_fee: float = 0.0\
    notes: Optional[str] = None\
\
class SessionCreate(BaseModel):\
    notary_id: str\
    client_ids: List[str]\
    location_type: str\
    meeting_address: Optional[str] = None\
    notes: Optional[str] = None\
    payment_status: models.PaymentStatus = models.PaymentStatus.unpaid\
    payment_method: Optional[models.PaymentMethod] = None\
    acts: List[ActCreate]\
\
# --- CLIENT ENDPOINTS ---\
\
@app.post("/api/clients", status_code=status.HTTP_201_CREATED)\
def create_client(client: ClientCreate, db: Session = Depends(get_db)):\
    db_client = models.Client(**client.model_dump())\
    db.add(db_client)\
    db.commit()\
    db.refresh(db_client)\
    return db_client\
\
@app.get("/api/clients")\
def get_clients(db: Session = Depends(get_db)):\
    return db.query(models.Client).all()\
\
# --- JOURNAL / SESSION ENDPOINTS ---\
\
@app.post("/api/sessions", status_code=status.HTTP_201_CREATED)\
def create_notarial_session(session_data: SessionCreate, db: Session = Depends(get_db)):\
    # 1. Verify clients exist\
    clients = db.query(models.Client).filter(models.Client.client_id.in_(session_data.client_ids)).all()\
    if len(clients) != len(session_data.client_ids):\
        raise HTTPException(status_code=400, detail="One or more client IDs are invalid.")\
    \
    # 2. Calculate totals from nested acts\
    total_fee = sum(act.statutory_fee + act.additional_fee for act in session_data.acts)\
\
    # 3. Create Session instance\
    db_session = models.NotarialSession(\
        notary_id=session_data.notary_id,\
        location_type=session_data.location_type,\
        meeting_address=session_data.meeting_address,\
        notes=session_data.notes,\
        total_fee=total_fee,\
        payment_status=session_data.payment_status,\
        payment_method=session_data.payment_method\
    )\
    \
    # Attach clients via junction link\
    db_session.clients = clients\
    db.add(db_session)\
    db.flush() # Secure the session ID\
\
    # 4. Handle nested documents and individual act entries\
    for act_item in session_data.acts:\
        db_doc = models.Document(\
            document_title=act_item.document.document_title,\
            page_count=act_item.document.page_count\
        )\
        db.add(db_doc)\
        db.flush()\
\
        db_act = models.ActDocument(\
            session_id=db_session.session_id,\
            document_id=db_doc.document_id,\
            act_type=act_item.act_type,\
            statutory_fee=act_item.statutory_fee,\
            additional_fee=act_item.additional_fee,\
            notes=act_item.notes\
        )\
        db.add(db_act)\
\
    db.commit()\
    db.refresh(db_session)\
    return \{"message": "Session and journal entry recorded successfully", "session_id": db_session.session_id\}\
\
@app.get("/api/sessions")\
def get_journal_ledger(db: Session = Depends(get_db)):\
    # Query sessions eager loading related entities for the journal grid\
    sessions = db.query(models.NotarialSession).all()\
    \
    output = []\
    for s in sessions:\
        output.append(\{\
            "session_id": s.session_id,\
            "date": s.session_date,\
            "location_type": s.location_type,\
            "total_fee": float(s.total_fee),\
            "payment_status": s.payment_status,\
            "clients": [\{"id": c.client_id, "name": f"\{c.first_name\} \{c.last_name\}"\} for c in s.clients],\
            "acts_count": len(s.acts)\
        \})\
    return output\
}
