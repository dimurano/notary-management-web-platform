from datetime import datetime
import enum
from typing import List, Optional
from uuid import uuid4
from decimal import Decimal
from sqlalchemy import (
    Column,
    String,
    Boolean,
    Integer,
    Numeric,
    DateTime,
    Date,
    ForeignKey,
    Table,
    Enum as SQLEnum,
    Index,
    CheckConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

# Enums
class IdType(str, enum.Enum):
    drivers_license = "Drivers License"
    passport = "Passport"
    state_id = "State ID"
    military_id = "Military ID"
    other = "Other"

class ActType(str, enum.Enum):
    acknowledgment = "Acknowledgment"
    jurat = "Jurat"
    oath_affirmation = "Oath/Affirmation"
    copy_certification = "Copy Certification"
    signature_witnessing = "Signature Witnessing"

class PaymentStatus(str, enum.Enum):
    unpaid = "Unpaid"
    partially_paid = "Partially Paid"
    paid = "Paid"
    waived = "Waived"

class PaymentMethod(str, enum.Enum):
    cash = "Cash"
    credit_card = "Credit Card"
    debit_card = "Debit Card"
    check = "Check"
    digital_wallet = "Digital Wallet"

# Junction Table for Client-Session Many-to-Many relationship
client_sessions = Table(
    'client_sessions',
    Base.metadata,
    Column('session_id', ForeignKey('notarial_sessions.session_id', ondelete='CASCADE'), primary_key=True),
    Column('client_id', ForeignKey('clients.client_id', ondelete='RESTRICT'), primary_key=True),
    Column('role', String(30), default='Signer'),
    Column('signature_type', String(20), default='Wet')
)

class Notary(Base):
    __tablename__ = 'notaries'
    notary_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    email = Column(String(100), unique=True, nullable=False, index=True)
    phone = Column(String(20))
    commission_number = Column(String(50), nullable=False, unique=True, index=True)
    commission_expires = Column(Date, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<Notary {self.first_name} {self.last_name} ({self.notary_id})>"

class Client(Base):
    __tablename__ = 'clients'
    client_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    email = Column(String(100), index=True)
    phone = Column(String(20))
    street_address = Column(String(150))
    city = Column(String(50))
    state = Column(String(2))
    zip_code = Column(String(10))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    
    identifications = relationship("ClientIdentification", back_populates="client", cascade="all, delete-orphan")
    sessions = relationship("NotarialSession", secondary=client_sessions, back_populates="clients")

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<Client {self.first_name} {self.last_name} ({self.client_id})>"

class ClientIdentification(Base):
    __tablename__ = 'client_identifications'
    id_verification_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    client_id = Column(String(36), ForeignKey('clients.client_id', ondelete='CASCADE'), index=True)
    identification_type = Column(SQLEnum(IdType, native_enum=False), nullable=False)
    id_number = Column(String(50), nullable=False)
    issuer_state_country = Column(String(50), nullable=False)
    issue_date = Column(Date)
    expiry_date = Column(Date, nullable=False)
    
    client = relationship("Client", back_populates="identifications")

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<ClientIdentification {self.id_verification_id} type={self.identification_type}>"

class NotarialSession(Base):
    __tablename__ = 'notarial_sessions'
    session_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    notary_id = Column(String(36), ForeignKey('notaries.notary_id'), index=True)
    session_date = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    location_type = Column(String(20), nullable=False)
    meeting_address = Column(String(255))
    notes = Column(String)
    total_fee = Column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    payment_status = Column(SQLEnum(PaymentStatus, native_enum=False), default=PaymentStatus.unpaid, index=True)
    payment_method = Column(SQLEnum(PaymentMethod, native_enum=False))

    # RON / e-signature fields
    is_ron = Column(Boolean, default=False, nullable=False)
    ron_platform = Column(String(100))  # e.g., 'DocuSign RON', 'Notarize'
    session_audio_video_url = Column(String(500))
    tamper_evident_seal_id = Column(String(100))

    clients = relationship("Client", secondary=client_sessions, back_populates="sessions")
    acts = relationship("ActDocument", back_populates="session", cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint('total_fee >= 0', name='ck_notarial_sessions_total_fee_non_negative'),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<NotarialSession {self.session_id} date={self.session_date} notary={self.notary_id}>"

class Document(Base):
    __tablename__ = 'documents'
    document_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    document_title = Column(String(150), nullable=False)
    page_count = Column(Integer, default=1)
    file_path_hash = Column(String(255), index=True)

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<Document {self.document_title} ({self.document_id})>"

class ActDocument(Base):
    __tablename__ = 'act_documents'
    act_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    session_id = Column(String(36), ForeignKey('notarial_sessions.session_id', ondelete='CASCADE'), index=True)
    document_id = Column(String(36), ForeignKey('documents.document_id', ondelete='RESTRICT'), index=True)
    act_type = Column(SQLEnum(ActType, native_enum=False), nullable=False)
    statutory_fee = Column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    additional_fee = Column(Numeric(10, 2), default=Decimal("0.00"), nullable=False)
    notes = Column(String)
    
    session = relationship("NotarialSession", back_populates="acts")
    document = relationship("Document")

    __table_args__ = (
        CheckConstraint('statutory_fee >= 0', name='ck_act_documents_statutory_fee_non_negative'),
        CheckConstraint('additional_fee >= 0', name='ck_act_documents_additional_fee_non_negative'),
    )

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return f"<ActDocument {self.act_id} type={self.act_type}>"
