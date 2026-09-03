import pytest

from app.database import SessionLocal
from app.models import AuditLog, PatientOffer
from app.services.registration_service import DuplicateRegistrationError, register_patient_offer


def _register(db, mobile="9999999977"):
    return register_patient_offer(
        db,
        full_name="Service Test Patient",
        mobile=mobile,
        email="",
        age="",
        gender="",
        city="",
        doctor_name="",
        campaign_name="",
        campaign_id=1,
        offer_id=1,
        consent_given=True,
        actor="admin",
    )


def test_service_creates_legacy_patient_offer_and_audit(client):
    db = SessionLocal()
    try:
        coupon = _register(db)
        assert coupon.id is not None
        assert db.query(PatientOffer).count() == 1
        assert db.query(AuditLog).filter(AuditLog.action == "PATIENT_REGISTERED").count() == 1
    finally:
        db.close()


def test_service_preserves_weekly_duplicate_rule(client):
    db = SessionLocal()
    try:
        _register(db, mobile="9999999976")
        with pytest.raises(DuplicateRegistrationError):
            _register(db, mobile="9999999976")
    finally:
        db.close()