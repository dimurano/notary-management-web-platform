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
