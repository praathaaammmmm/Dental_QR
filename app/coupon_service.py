from datetime import datetime
from sqlalchemy import update
from sqlalchemy.orm import Session
from .models import PatientOffer

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
