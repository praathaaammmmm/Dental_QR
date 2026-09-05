"""QR credential lifecycle: issue, look up, validate, expire, and redeem.

Merged from the former ``app/qr_service.py`` (token/image issuance) and
``app/coupon_service.py`` (lookup/expiry/redemption) — both halves of one domain (the QR
credential itself), previously split across two flat top-level modules for no structural
reason. A QR token remains an opaque bearer credential: no patient PII is ever encoded
in it (see ``qr_payload``).
"""
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta
from pathlib import Path

import qrcode
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import QR_DIR, QR_SIGNING_KEY
from ..models import PatientOffer


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


def find_coupon(db: Session, token: str) -> PatientOffer | None:
    """Look up a coupon by either its human-visible ID (``SRD-XXXXXXXX``) or its raw
    secure token. Shared by every validate/redeem entry point (admin and staff) so the
    lookup rule can never drift between them.
    """
    value = token.strip()
    if re.fullmatch(r"SRD-[A-F0-9]{8}", value, re.IGNORECASE):
        coupon = db.execute(
            select(PatientOffer).where(PatientOffer.coupon_uid == value.upper())
        ).scalar_one_or_none()
        if coupon and coupon.secure_token_hash == token_hash(token_for(coupon.coupon_uid)):
            return coupon
        return None
    return db.execute(
        select(PatientOffer).where(PatientOffer.secure_token_hash == token_hash(value))
    ).scalar_one_or_none()


def result_for(coupon: PatientOffer) -> dict:
    """Classify a coupon's current state for the validate/redeem result screen."""
    if coupon.status == "REDEEMED": return {"kind": "REDEEMED", "coupon": coupon}
    if coupon.status == "CANCELLED": return {"kind": "CANCELLED", "coupon": coupon}
    if coupon.status == "EXPIRED": return {"kind": "EXPIRED", "coupon": coupon}
    return {"kind": "VALID", "coupon": coupon}


def refresh_expiry(coupon: PatientOffer, now: datetime) -> bool:
    if coupon.status == "ACTIVE" and now >= coupon.expires_at:
        coupon.status = "EXPIRED"
        return True
    return False


def redeem_atomic(db: Session, coupon_id: int, redeemed_by: str, now: datetime):
    # Conditional UPDATE makes ACTIVE -> REDEEMED a single atomic state transition.
    stmt = (
        update(PatientOffer)
        .where(
            PatientOffer.id == coupon_id,
            PatientOffer.status == "ACTIVE",
            PatientOffer.expires_at > now,
        )
        .values(status="REDEEMED", redeemed_at=now, redeemed_by=redeemed_by)
    )
    result = db.execute(stmt)
    db.commit()
    return result.rowcount == 1
