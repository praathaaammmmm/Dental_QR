import httpx

from app.database import SessionLocal
from app.models import DeliveryLog, Patient
from app.notifications.service import queue_manual_resend, queue_registration_deliveries
from app.registrations.service import register_patient_offer


def _register(db, mobile, email=""):
    return register_patient_offer(
        db, full_name="Delivery Intent Patient", mobile=mobile, email=email, age="", gender="",
        city="", doctor_name="", campaign_name="", campaign_id=1, offer_id=1,
        beneficiary_category="CGHS", consent_given=True, actor="admin",
    )


def test_registration_never_calls_n8n_inline(client, monkeypatch):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("registration must never call n8n inline")

    monkeypatch.setattr(httpx, "post", fail_if_called)
    db = SessionLocal()
    try:
        coupon = _register(db, "9200000000", email="inline@example.com")
        assert coupon.id is not None
    finally:
        db.close()


def test_registration_succeeds_even_if_httpx_would_raise(client, monkeypatch):
    """Registration must never be blocked or rolled back by n8n being unavailable."""
    def always_fail(*args, **kwargs):
        raise httpx.ConnectError("n8n is down")

    monkeypatch.setattr(httpx, "post", always_fail)
    response = client.post("/patients/register", data={
        "full_name": "Resilient Patient", "mobile": "9200000001", "campaign_id": "1",
        "offer_id": "1", "beneficiary_category": "CGHS", "consent_given": "true",
    }, follow_redirects=False)
    assert response.status_code == 303


def test_registration_with_both_contacts_creates_two_distinct_intents(client):
    db = SessionLocal()
    try:
        coupon = _register(db, "9200000002", email="both@example.com")
        rows = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).order_by(DeliveryLog.channel).all()
        assert len(rows) == 2
        assert {row.channel for row in rows} == {"EMAIL", "WHATSAPP"}
        assert rows[0].delivery_intent_key != rows[1].delivery_intent_key
        assert all(row.attempt_number == 1 for row in rows)
        assert all(row.status == "PREPARED" for row in rows)
        assert all(row.idempotency_key for row in rows)
        assert len({row.idempotency_key for row in rows}) == 2
    finally:
        db.close()


def test_registration_with_only_mobile_creates_one_whatsapp_intent(client):
    db = SessionLocal()
    try:
        coupon = _register(db, "9200000003")
        rows = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).all()
        assert len(rows) == 1
        assert rows[0].channel == "WHATSAPP"
        assert rows[0].status == "PREPARED"
        assert rows[0].attempt_number == 1
    finally:
        db.close()


def test_registration_with_neither_contact_creates_no_intents(client):
    db = SessionLocal()
    try:
        coupon = _register(db, "9200000004", email="temp@example.com")
        patient = db.get(Patient, coupon.patient_id)
        patient.mobile = ""
        patient.email = None
        db.query(DeliveryLog).filter_by(coupon_id=coupon.id).delete()
        db.commit()

        created = queue_registration_deliveries(db, patient, coupon, actor="admin")
        db.commit()

        assert created == []
        assert db.query(DeliveryLog).filter_by(coupon_id=coupon.id).count() == 0
    finally:
        db.close()


def test_manual_resend_creates_new_intent_not_a_retry_of_registration(client):
    db = SessionLocal()
    try:
        coupon = _register(db, "9200000005", email="resend@example.com")
        patient = db.get(Patient, coupon.patient_id)
        original_rows = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).all()
        original_keys = {row.delivery_intent_key for row in original_rows}

        resent = queue_manual_resend(db, patient, coupon, "EMAIL", actor="admin")

        assert resent.attempt_number == 1
        assert resent.delivery_intent_key not in original_keys
        assert resent.status == "PREPARED"
        for row in original_rows:
            db.refresh(row)
        assert {row.status for row in original_rows} == {"PREPARED"}
    finally:
        db.close()


def test_manual_resend_via_admin_route_returns_delivery_queued_message(client):
    db = SessionLocal()
    try:
        coupon = _register(db, "9200000006", email="uiresend@example.com")
        patient_id = coupon.patient_id
    finally:
        db.close()

    response = client.post(f"/patients/{patient_id}/delivery/email", follow_redirects=False)
    assert response.status_code == 303
    assert "queued" in response.headers["location"].lower()


def test_manual_resend_via_staff_route_returns_delivery_queued_message(client):
    from tests.test_staff_interface import _login_as_staff

    db = SessionLocal()
    try:
        coupon = _register(db, "9200000007", email="staffresend@example.com")
        patient_id = coupon.patient_id
    finally:
        db.close()

    _login_as_staff(client)
    response = client.post(f"/staff/patients/{patient_id}/delivery/EMAIL", follow_redirects=False)
    assert response.status_code == 303
    assert "queued" in response.headers["location"].lower()
