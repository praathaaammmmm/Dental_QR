"""Scheduled expiry maintenance for QR registrations.

Run by ``python -m app.expiry_job`` from one external scheduler/worker only.
The validation and redemption paths remain the authority at request time.
"""
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit_service import audit
from .models import AuditLog, PatientOffer
from .n8n_service import trigger_delivery
from .time_utils import utc_now

SYSTEM_ACTOR = "system:expiry-sweep"
REMINDER_ACTION = "EXPIRY_REMINDER_TRIGGERED"


def _reminder_already_triggered(db: Session, coupon_id: int) -> bool:
    return db.execute(
        select(AuditLog.id).where(
            AuditLog.coupon_id == coupon_id,
            AuditLog.action == REMINDER_ACTION,
        ).limit(1)
    ).scalar_one_or_none() is not None


def _reminder_payload(coupon: PatientOffer) -> dict:
    patient = coupon.patient
    return {
        "event": "REGISTRATION_EXPIRY_REMINDER",
        "registration_id": coupon.coupon_uid,
        "patient": {
            "name": patient.full_name,
            "email": patient.email,
            "phone": patient.mobile,
        },
        "service": coupon.offer.name,
        "campaign": coupon.campaign.name if coupon.campaign else patient.campaign_name,
        "expires_at": coupon.expires_at.isoformat(),
    }


def run_expiry_sweep(db: Session, now: datetime | None = None) -> dict[str, int]:
    """Expire stale active offers and send one reminder for offers 24–48h out.

    The caller owns the database session. This function commits its state and
    audit records together after the existing n8n webhook boundary is called.
    It is deliberately suitable for one externally scheduled worker, avoiding
    in-process schedulers that would duplicate work across web replicas.
    """
    now = now or utc_now()
    expired = db.execute(
        select(PatientOffer).where(
            PatientOffer.status == "ACTIVE",
            PatientOffer.expires_at <= now,
        )
    ).scalars().all()
    for coupon in expired:
        coupon.status = "EXPIRED"
        audit(db, SYSTEM_ACTOR, "QR_AUTO_EXPIRED", coupon.id, coupon.patient_id, {
            "expires_at": coupon.expires_at.isoformat(),
        })

    reminder_start = now + timedelta(hours=24)
    reminder_end = now + timedelta(hours=48)
    reminder_candidates = db.execute(
        select(PatientOffer).where(
            PatientOffer.status == "ACTIVE",
            PatientOffer.expires_at >= reminder_start,
            PatientOffer.expires_at <= reminder_end,
        )
    ).scalars().all()
    reminders_triggered = 0
    for coupon in reminder_candidates:
        if _reminder_already_triggered(db, coupon.id):
            continue
        result = trigger_delivery(_reminder_payload(coupon))
        audit(db, SYSTEM_ACTOR, REMINDER_ACTION, coupon.id, coupon.patient_id, {
            "delivery_status": result["status"],
            "workflow_id": result.get("workflow_id"),
            "failure_reason": result.get("reason"),
        })
        reminders_triggered += 1

    db.commit()
    return {"expired": len(expired), "reminders_triggered": reminders_triggered}
