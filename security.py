{\rtf1\ansi\ansicpg1252\cocoartf2870
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 ArialMT;\f1\fmodern\fcharset0 Courier;}
{\colortbl;\red255\green255\blue255;\red0\green0\blue0;}
{\*\expandedcolortbl;;\cssrgb\c0\c0\c0;}
\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\deftab720
\pard\pardeftab720\partightenfactor0

\f0\fs40 \cf0 \expnd0\expndtw0\kerning0
python\
\pard\pardeftab720\partightenfactor0

\f1\fs28 \cf0 import os\
from cryptography.fernet import Fernet\
\
# In production, load this from an environment variable (e.g., os.environ.get("SECRET_KEY"))\
# To generate a new key run: Fernet.generate_key().decode()\
ENCRYPTION_KEY = b'uG9mZXRyaWNhbF9zZWN1cmVfa2V5X25vdGFyeV9mbG93XzEyMw=='\
fernet = Fernet(ENCRYPTION_KEY)\
\
def encrypt_data(plain_text: str) -> str:\
    if not plain_text:\
        return ""\
    return fernet.encrypt(plain_text.encode()).decode()\
\
def decrypt_data(cipher_text: str) -> str:\
    if not cipher_text:\
        return ""\
    try:\
        return fernet.decrypt(cipher_text.encode()).decode()\
    except Exception:\
        return "[DECRYPTION_ERROR: Invalid Key]"}