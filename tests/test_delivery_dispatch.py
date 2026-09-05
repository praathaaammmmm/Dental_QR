from datetime import timedelta

from sqlalchemy.exc import IntegrityError

from app.notifications import n8n as n8n_service
from app.database import SessionLocal
from app.models import DeliveryLog
from app.notifications import service as delivery_service
from app.notifications.service import (
    _claim_prepared_rows, _finish_sending_attempt, _recover_stale_sending,
    dispatch_pending_deliveries, maybe_retry_failed_intents,
)
from app.registrations.service import register_patient_offer
from app.time_utils import utc_now


def _register(db, mobile, email=""):
    return register_patient_offer(
        db, full_name="Dispatch Test Patient", mobile=mobile, email=email, age="", gender="",
        city="", doctor_name="", campaign_name="", campaign_id=1, offer_id=1,
        beneficiary_category="CGHS", consent_given=True, actor="admin",
    )


# --- Claiming --------------------------------------------------------------

def test_claim_only_takes_prepared_rows(client):
    db = SessionLocal()
    try:
        coupon = _register(db, "9300000001", email="claim@example.com")
        rows = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).all()
        rows[0].status = "SENT"
        db.commit()

        claimed = _claim_prepared_rows(db, utc_now())
        claimed_rows = db.query(DeliveryLog).filter(DeliveryLog.id.in_(claimed)).all()
        assert all(row.status == "SENDING" for row in claimed_rows)
        assert rows[0].id not in claimed
    finally:
        db.close()


def test_second_claim_attempt_finds_nothing_once_row_is_sending(client):
    db = SessionLocal()
    try:
        _register(db, "9300000002", email="claimrace@example.com")
        now = utc_now()
        first_claim = _claim_prepared_rows(db, now)
        second_claim = _claim_prepared_rows(db, now)
        assert len(first_claim) == 2  # email + whatsapp
        assert second_claim == []
    finally:
        db.close()


# --- Dispatch outcomes -------------------------------------------------------

def test_successful_dispatch_moves_row_to_sent(client, monkeypatch):
    monkeypatch.setattr(delivery_service, "N8N_WEBHOOK_URL", "https://n8n.example/webhook")
    monkeypatch.setattr(delivery_service, "trigger_delivery", lambda payload: {"status": "SENT", "workflow_id": "exec-1"})

    db = SessionLocal()
    try:
        coupon = _register(db, "9300000003")
        result = dispatch_pending_deliveries(db, now=utc_now())
        assert result["sent"] == 1
        row = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).one()
        assert row.status == "SENT"
        assert row.n8n_workflow_id == "exec-1"
        assert row.dispatched_at is not None
    finally:
        db.close()


def test_failed_dispatch_moves_row_to_failed_and_stays_retryable(client, monkeypatch):
    monkeypatch.setattr(delivery_service, "N8N_WEBHOOK_URL", "https://n8n.example/webhook")
    monkeypatch.setattr(delivery_service, "trigger_delivery", lambda payload: {"status": "FAILED", "reason": "n8n unreachable"})

    db = SessionLocal()
    try:
        coupon = _register(db, "9300000004")
        result = dispatch_pending_deliveries(db, now=utc_now())
        assert result["failed"] == 1
        row = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).one()
        assert row.status == "FAILED"
        assert row.retryable is True
        assert row.failure_reason == "n8n unreachable"
    finally:
        db.close()


def test_dispatch_with_unconfigured_n8n_claims_rows_and_reports_explicit_failure(client, monkeypatch):
    """A missing N8N_WEBHOOK_URL must never be indistinguishable from claimed: 0 when
    PREPARED rows exist — the dispatcher still claims and attempts them, and
    ``trigger_delivery``'s own guard turns "not configured" into an observable,
    retryable FAILED row with a clear reason instead of a silent no-op."""
    monkeypatch.setattr(n8n_service, "N8N_WEBHOOK_URL", "")

    db = SessionLocal()
    try:
        coupon = _register(db, "9300000005", email="unconfigured@example.com")
        result = dispatch_pending_deliveries(db, now=utc_now())
        assert result == {"claimed": 2, "sent": 0, "failed": 2, "stale_recovered": 0}
        rows = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).all()
        assert all(row.status == "FAILED" for row in rows)
        assert all(row.retryable is True for row in rows)
        assert all("N8N_WEBHOOK_URL is not configured" in row.failure_reason for row in rows)
    finally:
        db.close()


# --- Channel eligibility: a visible PREPARED row must always be claimed and attempted ------

def test_prepared_email_row_is_claimed_and_dispatched_to_n8n(client, monkeypatch):
    captured = []

    def fake_trigger(payload):
        captured.append(payload["channel"])
        return {"status": "SENT", "workflow_id": "exec-email"}

    monkeypatch.setattr(delivery_service, "trigger_delivery", fake_trigger)

    db = SessionLocal()
    try:
        coupon = _register(db, "9300000016", email="email-row@example.com")
        result = dispatch_pending_deliveries(db, now=utc_now())
        assert result["claimed"] == 2  # email + whatsapp both visible and eligible
        assert result["sent"] == 2
        assert "EMAIL" in captured

        email_row = db.query(DeliveryLog).filter_by(coupon_id=coupon.id, channel="EMAIL").one()
        assert email_row.status == "SENT"
        assert email_row.n8n_workflow_id == "exec-email"
    finally:
        db.close()


def test_prepared_whatsapp_row_is_claimed_and_reaches_its_documented_n8n_failure(client, monkeypatch):
    """The WhatsApp branch of the n8n workflow is a labeled placeholder (see n8n/README.md
    section E) that always reports a clear, non-permanent failure rather than silently
    doing nothing — the dispatcher must still claim and hand off the row to reach that
    path, not skip WhatsApp locally."""
    def fake_trigger(payload):
        assert payload["channel"] == "WHATSAPP"
        return {
            "status": "FAILED",
            "reason": "WhatsApp delivery is not yet configured for this clinic.",
        }

    monkeypatch.setattr(delivery_service, "trigger_delivery", fake_trigger)

    db = SessionLocal()
    try:
        coupon = _register(db, "9300000017")  # mobile only -> WHATSAPP row
        result = dispatch_pending_deliveries(db, now=utc_now())
        assert result["claimed"] == 1
        assert result["failed"] == 1

        row = db.query(DeliveryLog).filter_by(coupon_id=coupon.id, channel="WHATSAPP").one()
        assert row.status == "FAILED"
        assert row.retryable is True
        assert "not yet configured" in row.failure_reason
    finally:
        db.close()


# --- CLI worker must share the exact same database/config as the web app -------------------

def test_cli_delivery_job_uses_the_same_database_and_config_as_the_web_app():
    from app import delivery_job
    from app.database import SessionLocal as WebSessionLocal, engine as web_engine
    from app.database import engine as cli_engine

    assert delivery_job.SessionLocal is WebSessionLocal
    assert cli_engine is web_engine


def test_cli_delivery_job_sees_rows_created_through_the_web_app(client, monkeypatch):
    """A row visible on the CRM Delivery screen (created via the FastAPI app) must be
    claimable by a plain `python -m app.delivery_job` run against the same database."""
    from app import delivery_job

    monkeypatch.setattr(delivery_service, "trigger_delivery", lambda payload: {"status": "SENT", "workflow_id": "exec-cli"})

    db = SessionLocal()
    try:
        coupon = _register(db, "9300000018", email="cli-visible@example.com")
        coupon_id = coupon.id
    finally:
        db.close()

    cli_db = delivery_job.SessionLocal()
    try:
        result = dispatch_pending_deliveries(cli_db)
        assert result["claimed"] == 2
        assert result["sent"] == 2
    finally:
        cli_db.close()

    verify_db = SessionLocal()
    try:
        rows = verify_db.query(DeliveryLog).filter_by(coupon_id=coupon_id).all()
        assert all(row.status == "SENT" for row in rows)
    finally:
        verify_db.close()


# --- Race safety: dispatcher must not overwrite a row a callback already resolved --------

def test_dispatcher_does_not_overwrite_row_already_resolved_by_racing_callback(client):
    db = SessionLocal()
    try:
        coupon = _register(db, "9300000006")
        row = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).one()
        row.status = "SENDING"
        row.dispatched_at = utc_now()
        db.commit()

        # Simulate an n8n callback arriving and resolving the row before the dispatcher's
        # own outcome-persist step runs.
        row.status = "DELIVERED"
        db.commit()

        updated = _finish_sending_attempt(db, row.id, "SENT", {"n8n_workflow_id": "late-exec"})

        assert updated is False
        db.refresh(row)
        assert row.status == "DELIVERED"
        assert row.n8n_workflow_id is None
    finally:
        db.close()


# --- Stale SENDING recovery ---------------------------------------------------

def test_stale_sending_row_is_recovered_to_failed(client):
    db = SessionLocal()
    try:
        coupon = _register(db, "9300000007")
        row = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).one()
        row.status = "SENDING"
        row.dispatched_at = utc_now() - timedelta(seconds=1000)
        db.commit()

        recovered = _recover_stale_sending(db, utc_now())
        assert recovered == 1
        db.refresh(row)
        assert row.status == "FAILED"
        assert row.retryable is True
        assert "stale" in row.failure_reason.lower()
    finally:
        db.close()


def test_fresh_sending_row_is_not_recovered(client):
    db = SessionLocal()
    try:
        coupon = _register(db, "9300000008")
        row = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).one()
        row.status = "SENDING"
        row.dispatched_at = utc_now() - timedelta(seconds=5)
        db.commit()

        recovered = _recover_stale_sending(db, utc_now())
        assert recovered == 0
        db.refresh(row)
        assert row.status == "SENDING"
    finally:
        db.close()


# --- Retry logic ---------------------------------------------------------------

def test_retry_creates_new_row_same_intent_incremented_attempt(client):
    db = SessionLocal()
    try:
        coupon = _register(db, "9300000009")
        row = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).one()
        row.status = "FAILED"
        row.retryable = True
        row.sent_at = utc_now() - timedelta(minutes=5)
        db.commit()

        created = maybe_retry_failed_intents(db, now=utc_now())
        assert created == 1
        rows = db.query(DeliveryLog).filter_by(delivery_intent_key=row.delivery_intent_key).order_by(DeliveryLog.attempt_number).all()
        assert [r.attempt_number for r in rows] == [1, 2]
        assert rows[1].status == "PREPARED"
        assert rows[1].idempotency_key != rows[0].idempotency_key
    finally:
        db.close()


def test_retry_respects_backoff_timing(client):
    db = SessionLocal()
    try:
        coupon = _register(db, "9300000010")
        row = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).one()
        row.status = "FAILED"
        row.retryable = True
        row.sent_at = utc_now()  # just failed, backoff (2 minutes) not yet elapsed
        db.commit()

        not_yet = maybe_retry_failed_intents(db, now=utc_now() + timedelta(minutes=1))
        assert not_yet == 0

        now_due = maybe_retry_failed_intents(db, now=utc_now() + timedelta(minutes=3))
        assert now_due == 1
    finally:
        db.close()


def test_retry_stops_at_three_attempts(client):
    db = SessionLocal()
    try:
        coupon = _register(db, "9300000011")
        row = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).one()
        row.status = "FAILED"
        row.retryable = True
        row.attempt_number = 3
        row.sent_at = utc_now() - timedelta(hours=1)
        db.commit()

        created = maybe_retry_failed_intents(db, now=utc_now())
        assert created == 0
        assert db.query(DeliveryLog).filter_by(delivery_intent_key=row.delivery_intent_key).count() == 1
    finally:
        db.close()


def test_retry_skips_non_retryable_failures(client):
    db = SessionLocal()
    try:
        coupon = _register(db, "9300000012")
        row = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).one()
        row.status = "FAILED"
        row.retryable = False
        row.sent_at = utc_now() - timedelta(hours=1)
        db.commit()

        created = maybe_retry_failed_intents(db, now=utc_now())
        assert created == 0
    finally:
        db.close()


def test_retry_only_considers_latest_attempt_per_intent(client):
    """An old FAILED row from an earlier attempt must not be independently retried
    once a newer attempt exists for the same intent."""
    db = SessionLocal()
    try:
        coupon = _register(db, "9300000013")
        row = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).one()
        row.status = "FAILED"
        row.retryable = True
        row.sent_at = utc_now() - timedelta(hours=1)
        db.commit()

        db.add(DeliveryLog(
            coupon_id=row.coupon_id, channel=row.channel, recipient=row.recipient, status="SENDING",
            delivery_intent_key=row.delivery_intent_key, idempotency_key="dlv_manual_attempt2",
            attempt_number=2,
        ))
        db.commit()

        created = maybe_retry_failed_intents(db, now=utc_now())
        assert created == 0
        assert db.query(DeliveryLog).filter_by(delivery_intent_key=row.delivery_intent_key).count() == 2
    finally:
        db.close()


def test_unique_constraint_prevents_duplicate_attempt_number_for_intent(client):
    db = SessionLocal()
    try:
        coupon = _register(db, "9300000014")
        row = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).first()
        db.add(DeliveryLog(
            coupon_id=row.coupon_id, channel=row.channel, recipient=row.recipient, status="PREPARED",
            delivery_intent_key=row.delivery_intent_key, idempotency_key="dlv_dup_test",
            attempt_number=row.attempt_number,
        ))
        try:
            db.commit()
            assert False, "expected IntegrityError"
        except IntegrityError:
            db.rollback()
    finally:
        db.close()


# --- Callback URL construction ------------------------------------------------

def test_payload_callback_url_uses_n8n_callback_base_url_when_configured(client, monkeypatch):
    """n8n itself must be able to reach the CRM's callback endpoint. That address can
    differ from PUBLIC_BASE_URL (e.g. n8n running in Docker, where 127.0.0.1 resolves to
    the container, not the host) so callback_url must be built from the dedicated,
    n8n-reachable setting."""
    monkeypatch.setattr(delivery_service, "N8N_CALLBACK_BASE_URL", "http://host.docker.internal:8000")
    captured = []

    def fake_trigger(payload):
        captured.append(payload)
        return {"status": "SENT", "workflow_id": "exec-cb"}

    monkeypatch.setattr(delivery_service, "trigger_delivery", fake_trigger)

    db = SessionLocal()
    try:
        _register(db, "9300000019", email="callback-url@example.com")
        dispatch_pending_deliveries(db, now=utc_now())
        assert captured, "expected trigger_delivery to be called"
        for payload in captured:
            assert payload["callback_url"] == "http://host.docker.internal:8000/webhooks/n8n/delivery"
    finally:
        db.close()


def test_payload_callback_url_falls_back_to_public_base_url_when_unset(client, monkeypatch):
    """N8N_CALLBACK_BASE_URL defaults to PUBLIC_BASE_URL (config.py) when not set
    separately, so existing single-machine deployments keep working unchanged."""
    from app.config import PUBLIC_BASE_URL
    monkeypatch.setattr(delivery_service, "N8N_CALLBACK_BASE_URL", PUBLIC_BASE_URL)
    captured = []

    def fake_trigger(payload):
        captured.append(payload)
        return {"status": "SENT", "workflow_id": "exec-cb2"}

    monkeypatch.setattr(delivery_service, "trigger_delivery", fake_trigger)

    db = SessionLocal()
    try:
        _register(db, "9300000020", email="callback-fallback@example.com")
        dispatch_pending_deliveries(db, now=utc_now())
        assert captured, "expected trigger_delivery to be called"
        for payload in captured:
            assert payload["callback_url"] == f"{PUBLIC_BASE_URL}/webhooks/n8n/delivery"
    finally:
        db.close()


def test_retry_is_idempotent_across_repeated_ticks(client):
    db = SessionLocal()
    try:
        coupon = _register(db, "9300000015")
        row = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).one()
        row.status = "FAILED"
        row.retryable = True
        row.sent_at = utc_now() - timedelta(minutes=5)
        db.commit()

        now = utc_now()
        first = maybe_retry_failed_intents(db, now=now)
        second = maybe_retry_failed_intents(db, now=now)
        assert first == 1
        assert second == 0
        rows = db.query(DeliveryLog).filter_by(delivery_intent_key=row.delivery_intent_key).all()
        assert sorted(r.attempt_number for r in rows) == [1, 2]
    finally:
        db.close()
