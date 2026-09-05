from datetime import timedelta

from app.database import SessionLocal
from app.expiry_service import REMINDER_ACTION, run_expiry_sweep
from app.models import AuditLog, PatientOffer
from app.qr_service import token_for
from app.time_utils import utc_now


def _register(client, name: str, mobile: str):
    response = client.post("/patients/register", data={
        "full_name": name, "mobile": mobile, "campaign_id": "1",
        "offer_id": "1", "beneficiary_category": "CGHS", "consent_given": "true",
    })
    assert response.status_code == 200


def test_expiry_sweep_expires_stale_records_and_triggers_one_reminder(client, monkeypatch):
    _register(client, "Expired Sweep", "9000000001")
    _register(client, "Reminder Sweep", "9000000002")
    now = utc_now()
    db = SessionLocal()
    try:
        expired, reminder = db.query(PatientOffer).order_by(PatientOffer.id).all()
        expired.expires_at = now - timedelta(seconds=1)
        reminder.expires_at = now + timedelta(hours=30)
        db.commit()

        calls = []
        monkeypatch.setattr(
            "app.expiry_service.trigger_delivery",
            lambda payload: calls.append(payload) or {"status": "PENDING", "reason": "test"},
        )
        assert run_expiry_sweep(db, now) == {"expired": 1, "reminders_triggered": 1}
        assert db.get(PatientOffer, expired.id).status == "EXPIRED"
        assert db.query(AuditLog).filter_by(coupon_id=expired.id, action="QR_AUTO_EXPIRED").count() == 1
        assert db.query(AuditLog).filter_by(coupon_id=reminder.id, action=REMINDER_ACTION).count() == 1
        assert calls[0]["event"] == "REGISTRATION_EXPIRY_REMINDER"

        assert run_expiry_sweep(db, now) == {"expired": 0, "reminders_triggered": 0}
        assert len(calls) == 1
    finally:
        db.close()


def test_expiry_reminder_callback_url_uses_n8n_callback_base_url(client, monkeypatch):
    """Expiry reminders share the same callback-reachability concern as delivery
    dispatch: n8n must be able to reach the CRM, which is not always the same address
    the CRM considers its own public URL (e.g. n8n running in Docker)."""
    monkeypatch.setattr("app.expiry_service.N8N_CALLBACK_BASE_URL", "http://host.docker.internal:8000")
    _register(client, "Reminder Callback URL", "9000000004")
    now = utc_now()
    db = SessionLocal()
    try:
        coupon = db.query(PatientOffer).one()
        coupon.expires_at = now + timedelta(hours=30)
        db.commit()

        calls = []
        monkeypatch.setattr(
            "app.expiry_service.trigger_delivery",
            lambda payload: calls.append(payload) or {"status": "PENDING", "reason": "test"},
        )
        run_expiry_sweep(db, now)
        assert calls[0]["callback_url"] == "http://host.docker.internal:8000/webhooks/n8n/delivery"
    finally:
        db.close()


def test_validation_rejects_expired_registration_before_a_sweep_runs(client):
    _register(client, "Lazy Expiry", "9000000003")
    db = SessionLocal()
    try:
        coupon = db.query(PatientOffer).one()
        coupon.expires_at = utc_now() - timedelta(seconds=1)
        token = token_for(coupon.coupon_uid)
        coupon_id = coupon.id
        db.commit()
    finally:
        db.close()

    response = client.post("/validate", data={"token": token})
    assert "OFFER EXPIRED" in response.text
    db = SessionLocal()
    try:
        assert db.get(PatientOffer, coupon_id).status == "EXPIRED"
        assert db.query(AuditLog).filter_by(coupon_id=coupon_id, action="QR_EXPIRED").count() == 1
    finally:
        db.close()
