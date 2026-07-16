{\rtf1\ansi\ansicpg1252\cocoartf2870
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0

\f0\fs24 \cf0 from datetime import datetime\
import enum\
from typing import List, Optional\
from uuid import UUID, uuid4\
from sqlalchemy import create_engine, Column, String, Integer, Numeric, DateTime, Date, ForeignKey, Table, Enum\
from sqlalchemy.orm import declarative_base, relationship\
\
Base = declarative_base()\
\
# Enums\
class IdType(str, enum.Enum):\
    drivers_license = "Drivers License"\
    passport = "Passport"\
    state_id = "State ID"\
    military_id = "Military ID"\
    other = "Other"\
\
class ActType(str, enum.Enum):\
    acknowledgment = "Acknowledgment"\
    jurat = "Jurat"\
    oath_affirmation = "Oath/Affirmation"\
    copy_certification = "Copy Certification"\
    signature_witnessing = "Signature Witnessing"\
\
class PaymentStatus(str, enum.Enum):\
    unpaid = "Unpaid"\
    partially_paid = "Partially Paid"\
    paid = "Paid"\
    waived = "Waived"\
\
class PaymentMethod(str, enum.Enum):\
    cash = "Cash"\
    credit_card = "Credit Card"\
    debit_card = "Debit Card"\
    check = "Check"\
    digital_wallet = "Digital Wallet"\
\
# Junction Table for Client-Session Many-to-Many relationship\
client_sessions = Table(\
    'client_sessions',\
    Base.metadata,\
    Column('session_id', ForeignKey('notarial_sessions.session_id', ondelete='CASCADE'), primary_key=True),\
    Column('client_id', ForeignKey('clients.client_id', ondelete='RESTRICT'), primary_key=True),\
    Column('role', String(30), default='Signer'),\
    Column('signature_type', String(20), default='Wet')\
)\
\
class Notary(Base):\
    __tablename__ = 'notaries'\
    notary_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))\
    first_name = Column(String(50), nullable=False)\
    last_name = Column(String(50), nullable=False)\
    email = Column(String(100), unique=True, nullable=False)\
    phone = Column(String(20))\
    commission_number = Column(String(50), nullable=False)\
    commission_expires = Column(Date, nullable=False)\
    created_at = Column(DateTime, default=datetime.utcnow)\
\
class Client(Base):\
    __tablename__ = 'clients'\
    client_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))\
    first_name = Column(String(50), nullable=False)\
    last_name = Column(String(50), nullable=False)\
    email = Column(String(100))\
    phone = Column(String(20))\
    street_address = Column(String(150))\
    city = Column(String(50))\
    state = Column(String(2))\
    zip_code = Column(String(10))\
    created_at = Column(DateTime, default=datetime.utcnow)\
    \
    identifications = relationship("ClientIdentification", back_populates="client", cascade="all, delete-orphan")\
    sessions = relationship("NotarialSession", secondary=client_sessions, back_populates="clients")\
\
class ClientIdentification(Base):\
    __tablename__ = 'client_identifications'\
    id_verification_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))\
    client_id = Column(String(36), ForeignKey('clients.client_id', ondelete='CASCADE'))\
    identification_type = Column(Enum(IdType), nullable=False)\
    id_number = Column(String(50), nullable=False)\
    issuer_state_country = Column(String(50), nullable=False)\
    issue_date = Column(Date)\
    expiry_date = Column(Date, nullable=False)\
    \
    client = relationship("Client", back_populates="identifications")\
\
class NotarialSession(Base):\
    __tablename__ = 'notarial_sessions'\
    session_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))\
    notary_id = Column(String(36), ForeignKey('notaries.notary_id'))\
    session_date = Column(DateTime, nullable=False, default=datetime.utcnow)\
    location_type = Column(String(20), nullable=False)\
    meeting_address = Column(String(255))\
    notes = Column(String)\
    total_fee = Column(Numeric(10, 2), default=0.00)\
    payment_status = Column(Enum(PaymentStatus), default=PaymentStatus.unpaid)\
    payment_method = Column(Enum(PaymentMethod))\
    \
    clients = relationship("Client", secondary=client_sessions, back_populates="sessions")\
    acts = relationship("ActDocument", back_populates="session", cascade="all, delete-orphan")\
\
class Document(Base):\
    __tablename__ = 'documents'\
    document_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))\
    document_title = Column(String(150), nullable=False)\
    page_count = Column(Integer, default=1)\
    file_path_hash = Column(String(255))\
\
class ActDocument(Base):\
    __tablename__ = 'acts_documents'\
    act_id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))\
    session_id = Column(String(36), ForeignKey('notarial_sessions.session_id', ondelete='CASCADE'))\
    document_id = Column(String(36), ForeignKey('documents.document_id', ondelete='RESTRICT'))\
    act_type = Column(Enum(ActType), nullable=False)\
    statutory_fee = Column(Numeric(10, 2), default=0.00)\
    additional_fee = Column(Numeric(10, 2), default=0.00)\
    notes = Column(String)\
    \
    session = relationship("NotarialSession", back_populates="acts")\
    document = relationship("Document")\
}