from app.database import SessionLocal
from app.models import AuditLog, DeliveryLog
from app.registrations.service import register_patient_offer
from app.time_utils import utc_now

SECRET = "test-n8n-webhook-secret"
HEADERS = {"X-N8N-Webhook-Secret": SECRET}


def _register(db, mobile, email=""):
    return register_patient_offer(
        db, full_name="Webhook Test Patient", mobile=mobile, email=email, age="", gender="",
        city="", doctor_name="", campaign_name="", campaign_id=1, offer_id=1,
        beneficiary_category="CGHS", consent_given=True, actor="admin",
    )


def _row_in_status(client, mobile, status):
    db = SessionLocal()
    try:
        coupon = _register(db, mobile)
        row = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).one()
        row.status = status
        if status in {"SENDING", "SENT"}:
            row.dispatched_at = utc_now()
        db.commit()
        return row.idempotency_key
    finally:
        db.close()


def _post(client, payload, headers=HEADERS):
    return client.post("/webhooks/n8n/delivery", json=payload, headers=headers, include_csrf=False)


# --- Authentication -----------------------------------------------------------

def test_missing_secret_returns_401(client):
    response = _post(client, {"idempotency_key": "x", "status": "SENT"}, headers={})
    assert response.status_code == 401


def test_wrong_secret_returns_401(client):
    response = _post(client, {"idempotency_key": "x", "status": "SENT"}, headers={"X-N8N-Webhook-Secret": "wrong"})
    assert response.status_code == 401


# --- Validation -----------------------------------------------------------

def test_missing_idempotency_key_returns_400(client):
    response = _post(client, {"status": "SENT"})
    assert response.status_code == 400


def test_unknown_idempotency_key_returns_404(client):
    response = _post(client, {"idempotency_key": "dlv_does_not_exist", "status": "SENT"})
    assert response.status_code == 404


def test_invalid_status_value_returns_400(client):
    key = _row_in_status(client, "9400000001", "SENDING")
    response = _post(client, {"idempotency_key": key, "status": "BOGUS"})
    assert response.status_code == 400


# --- Legal transitions (Option A) -----------------------------------------------

def test_sending_to_sent_is_legal(client):
    key = _row_in_status(client, "9400000002", "SENDING")
    response = _post(client, {"idempotency_key": key, "status": "SENT", "provider_message_id": "pmid-1"})
    assert response.status_code == 200
    db = SessionLocal()
    try:
        row = db.query(DeliveryLog).filter_by(idempotency_key=key).one()
        assert row.status == "SENT"
        assert row.provider_message_id == "pmid-1"
    finally:
        db.close()


def test_sending_to_failed_is_legal(client):
    key = _row_in_status(client, "9400000003", "SENDING")
    response = _post(client, {"idempotency_key": key, "status": "FAILED", "failure_reason": "bounced", "permanent": False})
    assert response.status_code == 200
    db = SessionLocal()
    try:
        row = db.query(DeliveryLog).filter_by(idempotency_key=key).one()
        assert row.status == "FAILED"
        assert row.failure_reason == "bounced"
        assert row.retryable is True
    finally:
        db.close()


def test_sent_to_delivered_is_legal(client):
    key = _row_in_status(client, "9400000004", "SENT")
    response = _post(client, {"idempotency_key": key, "status": "DELIVERED"})
    assert response.status_code == 200
    db = SessionLocal()
    try:
        row = db.query(DeliveryLog).filter_by(idempotency_key=key).one()
        assert row.status == "DELIVERED"
        assert row.delivered_at is not None
    finally:
        db.close()


def test_sent_to_failed_is_legal(client):
    key = _row_in_status(client, "9400000005", "SENT")
    response = _post(client, {"idempotency_key": key, "status": "FAILED", "permanent": True})
    assert response.status_code == 200
    db = SessionLocal()
    try:
        row = db.query(DeliveryLog).filter_by(idempotency_key=key).one()
        assert row.status == "FAILED"
        assert row.retryable is False
    finally:
        db.close()


def test_whatsapp_not_configured_callback_marks_previously_sent_attempt_as_failed_non_retryable(client):
    """Mirrors the exact callback body n8n's 'Build FAILED Callback (WhatsApp Not
    Configured)' node produces (n8n/crm-qr-delivery.json). The CRM dispatcher marks a
    WHATSAPP row SENT as soon as n8n's webhook acknowledges receipt (responseMode
    onReceived) — the row only reaches its real, final state once this callback arrives
    from the (intentionally unconfigured) WhatsApp branch. A missing provider credential
    cannot self-heal by retrying, so this callback's permanent=true must leave the row
    non-retryable rather than eligible for another attempt."""
    key = _row_in_status(client, "9400000013", "SENT")
    response = _post(client, {
        "idempotency_key": key,
        "status": "FAILED",
        "provider_message_id": None,
        "failure_reason": (
            "WhatsApp delivery is not yet configured for this clinic. Configure a Meta "
            "WhatsApp Cloud API or Twilio WhatsApp credential in n8n to enable this channel."
        ),
        "permanent": True,
    })
    assert response.status_code == 200
    db = SessionLocal()
    try:
        row = db.query(DeliveryLog).filter_by(idempotency_key=key).one()
        assert row.status == "FAILED"
        assert row.retryable is False
        assert "not yet configured" in row.failure_reason
    finally:
        db.close()


# --- Illegal transitions -----------------------------------------------

def test_sending_to_delivered_is_rejected(client):
    key = _row_in_status(client, "9400000006", "SENDING")
    response = _post(client, {"idempotency_key": key, "status": "DELIVERED"})
    assert response.status_code == 409
    db = SessionLocal()
    try:
        row = db.query(DeliveryLog).filter_by(idempotency_key=key).one()
        assert row.status == "SENDING"
    finally:
        db.close()


def test_delivered_to_sent_is_rejected(client):
    key = _row_in_status(client, "9400000007", "DELIVERED")
    response = _post(client, {"idempotency_key": key, "status": "SENT"})
    assert response.status_code == 409


# --- Duplicate / terminal no-op -----------------------------------------------

def test_duplicate_delivered_callback_is_a_noop(client):
    key = _row_in_status(client, "9400000008", "DELIVERED")
    response = _post(client, {"idempotency_key": key, "status": "DELIVERED"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "noop": True}


def test_duplicate_callback_does_not_create_duplicate_audit_entry(client):
    key = _row_in_status(client, "9400000009", "SENDING")
    first = _post(client, {"idempotency_key": key, "status": "SENT"})
    assert first.status_code == 200

    db = SessionLocal()
    try:
        row = db.query(DeliveryLog).filter_by(idempotency_key=key).one()
        count_after_first = db.query(AuditLog).filter_by(coupon_id=row.coupon_id, action=f"{row.channel}_DELIVERY_SENT").count()
    finally:
        db.close()
    assert count_after_first == 1

    second = _post(client, {"idempotency_key": key, "status": "SENT"})
    assert second.status_code == 200
    assert second.json() == {"status": "ok", "noop": True}

    db = SessionLocal()
    try:
        count_after_second = db.query(AuditLog).filter_by(coupon_id=row.coupon_id, action=f"{row.channel}_DELIVERY_SENT").count()
    finally:
        db.close()
    assert count_after_second == 1


# --- Legacy compatibility -----------------------------------------------

def test_legacy_fallback_disabled_by_default_returns_404_for_null_key_row(client):
    db = SessionLocal()
    try:
        coupon = _register(db, "9400000010")
        row = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).one()
        row.status = "SENDING"
        row.idempotency_key = None
        db.commit()
        registration_id = coupon.coupon_uid
    finally:
        db.close()

    response = _post(client, {"idempotency_key": "dlv_unrelated", "status": "SENT", "registration_id": registration_id})
    assert response.status_code == 404


def test_legacy_fallback_works_when_flag_enabled_for_null_key_row(client, monkeypatch):
    from app.notifications import routes as notifications_routes
    monkeypatch.setattr(notifications_routes, "N8N_WEBHOOK_LEGACY_CALLBACK_COMPAT", True)

    db = SessionLocal()
    try:
        coupon = _register(db, "9400000011")
        row = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).one()
        row.status = "SENDING"
        row.idempotency_key = None
        db.commit()
        registration_id = coupon.coupon_uid

    finally:
        db.close()

    response = _post(client, {"idempotency_key": "dlv_unrelated", "status": "SENT", "registration_id": registration_id})
    assert response.status_code == 200

    db = SessionLocal()
    try:
        row = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).one()
        assert row.status == "SENT"
    finally:
        db.close()


def test_legacy_fallback_never_matches_a_modern_keyed_row_even_when_flag_enabled(client, monkeypatch):
    from app.notifications import routes as notifications_routes
    monkeypatch.setattr(notifications_routes, "N8N_WEBHOOK_LEGACY_CALLBACK_COMPAT", True)

    db = SessionLocal()
    try:
        coupon = _register(db, "9400000012")
        row = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).one()
        row.status = "SENDING"  # keeps its real idempotency_key, not NULL
        db.commit()
        registration_id = coupon.coupon_uid
    finally:
        db.close()

    response = _post(client, {"idempotency_key": "dlv_unrelated", "status": "SENT", "registration_id": registration_id})
    assert response.status_code == 404
