from datetime import timedelta

from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import DeliveryLog
from app.services import delivery_service
from app.services.delivery_service import (
    _claim_prepared_rows, _finish_sending_attempt, _recover_stale_sending,
    dispatch_pending_deliveries, maybe_retry_failed_intents,
)
from app.services.registration_service import register_patient_offer
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


def test_dispatch_with_unconfigured_n8n_leaves_prepared_rows_untouched(client, monkeypatch):
    monkeypatch.setattr(delivery_service, "N8N_WEBHOOK_URL", "")

    db = SessionLocal()
    try:
        coupon = _register(db, "9300000005", email="unconfigured@example.com")
        result = dispatch_pending_deliveries(db, now=utc_now())
        assert result == {"claimed": 0, "sent": 0, "failed": 0, "stale_recovered": 0}
        rows = db.query(DeliveryLog).filter_by(coupon_id=coupon.id).all()
        assert all(row.status == "PREPARED" for row in rows)
    finally:
        db.close()


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
