import hashlib
import hmac
import secrets
from datetime import datetime, timedelta
from pathlib import Path
import qrcode
from .config import QR_DIR, QR_SIGNING_KEY

def token_for(coupon_uid: str) -> str:
    signature = hmac.new(QR_SIGNING_KEY.encode(), coupon_uid.encode(), hashlib.sha256).hexdigest()
    return f"SRD-{coupon_uid}.{signature}"

def token_hash(token: str) -> str:
    return hashlib.sha256(token.strip().encode()).hexdigest()

def new_uid(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(4).upper()}"

def expiry_for(created_at: datetime) -> datetime:
    return created_at + timedelta(days=10)

def qr_payload(token: str) -> str:
    # Only the opaque secure token is encoded. No patient information is embedded.
    return token

def generate_qr(token: str, coupon_uid: str) -> Path:
    img = qrcode.make(qr_payload(token))
    path = QR_DIR / f"{coupon_uid}.png"
    img.save(path)
    return path

def ensure_qr(coupon_uid: str, expected_hash: str) -> Path:
    path = QR_DIR / f"{coupon_uid}.png"
    if not path.exists():
        token = token_for(coupon_uid)
        if not hmac.compare_digest(token_hash(token), expected_hash):
            raise FileNotFoundError("Legacy QR cannot be regenerated; issue a replacement coupon")
        generate_qr(token, coupon_uid)
    return path
