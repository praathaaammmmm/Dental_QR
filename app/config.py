import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'smritiraj.db'}")
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "10"))
DB_POOL_TIMEOUT_SECONDS = int(os.getenv("DB_POOL_TIMEOUT_SECONDS", "30"))
APP_ENV = os.getenv("APP_ENV", "development").lower()
CLINIC_USERNAME = os.getenv("CLINIC_USERNAME", "smritiraj-clinic")
CLINIC_PASSWORD_HASH = os.getenv("CLINIC_PASSWORD_HASH", "")
SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY", "")
QR_SIGNING_KEY_CONFIGURED = bool(os.getenv("QR_SIGNING_KEY", ""))
QR_SIGNING_KEY = os.getenv("QR_SIGNING_KEY", SESSION_SECRET_KEY)
SESSION_MAX_AGE_SECONDS = int(os.getenv("SESSION_MAX_AGE_SECONDS", "1800"))
SESSION_HTTPS_ONLY = os.getenv("SESSION_HTTPS_ONLY", "false").lower() == "true"
SESSION_VERSION = os.getenv("SESSION_VERSION", "1")
ALLOWED_HOSTS = [host.strip() for host in os.getenv(
    "ALLOWED_HOSTS", "127.0.0.1,localhost,testserver,healthcheck.railway.app"
).split(",") if host.strip()]
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
HOSPITAL_NAME = os.getenv("HOSPITAL_NAME", "Smriti Raj Dentistry")
N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "")
N8N_WEBHOOK_SECRET = os.getenv("N8N_WEBHOOK_SECRET", "")
SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "")
WHATSAPP_ENABLED = os.getenv("WHATSAPP_ENABLED", "false").lower() == "true"
WHATSAPP_API_TOKEN = os.getenv("WHATSAPP_API_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
VALIDATION_RATE_LIMIT_ATTEMPTS = int(os.getenv("VALIDATION_RATE_LIMIT_ATTEMPTS", "30"))
VALIDATION_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("VALIDATION_RATE_LIMIT_WINDOW_SECONDS", "60"))
BACKUP_ENCRYPTION_KEY = os.getenv("BACKUP_ENCRYPTION_KEY", "")
BACKUP_DIR = Path(os.getenv("BACKUP_DIR", str(BASE_DIR / "backups"))).resolve()
BACKUP_RETENTION_DAYS = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))
QR_DIR = BASE_DIR / "generated_qr"
QR_DIR.mkdir(exist_ok=True)

def validate_security_config() -> None:
    errors = []
    if not CLINIC_PASSWORD_HASH.startswith("$argon2"):
        errors.append("CLINIC_PASSWORD_HASH must contain an Argon2 password hash")
    if len(SESSION_SECRET_KEY) < 32:
        errors.append("SESSION_SECRET_KEY must be at least 32 characters")
    if len(QR_SIGNING_KEY) < 32:
        errors.append("QR_SIGNING_KEY must be at least 32 characters")
    if SESSION_MAX_AGE_SECONDS < 300:
        errors.append("SESSION_MAX_AGE_SECONDS must be at least 300")
    if APP_ENV == "production" and not SESSION_HTTPS_ONLY:
        errors.append("SESSION_HTTPS_ONLY must be true in production")
    if APP_ENV == "production" and not QR_SIGNING_KEY_CONFIGURED:
        errors.append("QR_SIGNING_KEY must be set separately in production")
    if APP_ENV in {"production", "staging"} and not BACKUP_ENCRYPTION_KEY:
        errors.append("BACKUP_ENCRYPTION_KEY must be set in production-like environments")
    if APP_ENV == "production" and not DATABASE_URL.startswith(("postgresql://", "postgresql+psycopg://")):
        errors.append("DATABASE_URL must use PostgreSQL in production")
    if APP_ENV == "production" and not PUBLIC_BASE_URL.startswith("https://"):
        errors.append("PUBLIC_BASE_URL must use HTTPS in production")
    if APP_ENV == "production" and (not ALLOWED_HOSTS or "*" in ALLOWED_HOSTS):
        errors.append("ALLOWED_HOSTS must explicitly list production hosts")
    if DB_POOL_SIZE < 1 or DB_MAX_OVERFLOW < 0 or DB_POOL_TIMEOUT_SECONDS < 1:
        errors.append("Database pool settings must be positive")
    if VALIDATION_RATE_LIMIT_ATTEMPTS < 1 or VALIDATION_RATE_LIMIT_WINDOW_SECONDS < 1:
        errors.append("Validation rate-limit settings must be positive")
    if BACKUP_RETENTION_DAYS < 1:
        errors.append("BACKUP_RETENTION_DAYS must be at least 1")
    if errors:
        raise RuntimeError("Invalid security configuration: " + "; ".join(errors))
