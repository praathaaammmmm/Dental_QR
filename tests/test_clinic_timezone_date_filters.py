"""Regression coverage for Asia/Kolkata-local date filtering near midnight.

Rule under test (see app/time_utils.py):
- User-entered start/end dates on the staff patient list and the admin dashboard/report
  filters represent clinic-local (Asia/Kolkata) calendar dates, never UTC dates.
- The end date is inclusive of its entire local calendar day.
- Stored timestamps are naive UTC (`app.time_utils.utc_now()`); comparisons must convert
  the local calendar-date range to UTC bounds before filtering, regardless of exactly how
  a given timestamp column happens to be represented.
"""
from datetime import date, timedelta

from app.database import SessionLocal
from app.models import Campaign, Offer, PatientOffer
from app.services.analytics_service import dashboard_summary
from app.time_utils import clinic_local_day_start_utc
from tests.test_staff_interface import _login_as_staff

ANCHOR_DAY = date(2026, 1, 15)  # arbitrary fixed local calendar date, away from any real "today"


def _staff_register(client, name, mobile):
    response = client.post("/staff/register", data={
        "full_name": name, "mobile": mobile, "campaign_id": "1", "offer_id": "1",
        "beneficiary_category": "CGHS", "consent_given": "true",
    }, follow_redirects=False)
    assert response.status_code == 303


def _set_created_at(coupon_id, when):
    db = SessionLocal()
    try:
        coupon = db.get(PatientOffer, coupon_id)
        coupon.created_at = when
        db.commit()
    finally:
        db.close()


def _register_and_set(client, name, mobile, when):
    _staff_register(client, name, mobile)
    db = SessionLocal()
    try:
        coupon = db.query(PatientOffer).filter(PatientOffer.patient.has(full_name=name)).one()
        coupon_id = coupon.id
    finally:
        db.close()
    _set_created_at(coupon_id, when)
    return coupon_id


def test_record_just_before_local_midnight_belongs_to_the_earlier_local_day(client):
    _login_as_staff(client)
    just_before_midnight = clinic_local_day_start_utc(ANCHOR_DAY) - timedelta(seconds=1)
    _register_and_set(client, "Just Before Midnight Patient", "9500000001", just_before_midnight)

    earlier_day_page = client.get(f"/staff/patients?start={(ANCHOR_DAY - timedelta(days=1)).isoformat()}&end={(ANCHOR_DAY - timedelta(days=1)).isoformat()}")
    assert "Just Before Midnight Patient" in earlier_day_page.text

    anchor_day_page = client.get(f"/staff/patients?start={ANCHOR_DAY.isoformat()}&end={ANCHOR_DAY.isoformat()}")
    assert "Just Before Midnight Patient" not in anchor_day_page.text


def test_record_just_after_local_midnight_belongs_to_the_later_local_day(client):
    _login_as_staff(client)
    just_after_midnight = clinic_local_day_start_utc(ANCHOR_DAY) + timedelta(seconds=1)
    _register_and_set(client, "Just After Midnight Patient", "9500000002", just_after_midnight)

    anchor_day_page = client.get(f"/staff/patients?start={ANCHOR_DAY.isoformat()}&end={ANCHOR_DAY.isoformat()}")
    assert "Just After Midnight Patient" in anchor_day_page.text

    earlier_day_page = client.get(f"/staff/patients?start={(ANCHOR_DAY - timedelta(days=1)).isoformat()}&end={(ANCHOR_DAY - timedelta(days=1)).isoformat()}")
    assert "Just After Midnight Patient" not in earlier_day_page.text


def test_end_date_is_inclusive_through_the_final_second_of_the_local_day(client):
    _login_as_staff(client)
    last_second_of_day = clinic_local_day_start_utc(ANCHOR_DAY + timedelta(days=1)) - timedelta(seconds=1)
    _register_and_set(client, "Last Second Of Day Patient", "9500000003", last_second_of_day)

    page = client.get(f"/staff/patients?start={ANCHOR_DAY.isoformat()}&end={ANCHOR_DAY.isoformat()}")
    assert "Last Second Of Day Patient" in page.text

    next_day_page = client.get(f"/staff/patients?start={(ANCHOR_DAY + timedelta(days=1)).isoformat()}&end={(ANCHOR_DAY + timedelta(days=1)).isoformat()}")
    assert "Last Second Of Day Patient" not in next_day_page.text


def test_combined_staff_filters_with_deterministic_midnight_adjacent_records(client):
    _login_as_staff(client)
    db = SessionLocal()
    try:
        other_campaign = Campaign(
            name="Midnight Test Second Campaign",
            start_date=ANCHOR_DAY - timedelta(days=30), end_date=ANCHOR_DAY + timedelta(days=30),
            status="ACTIVE", created_by="test",
        )
        other_campaign.offers = db.query(Offer).all()
        db.add(other_campaign)
        db.commit()
        other_campaign_id = other_campaign.id
    finally:
        db.close()

    _register_and_set(
        client, "Combo In Range Patient", "9500000004",
        clinic_local_day_start_utc(ANCHOR_DAY) + timedelta(hours=6),
    )
    _register_and_set(
        client, "Combo Wrong Day Patient", "9500000005",
        clinic_local_day_start_utc(ANCHOR_DAY) - timedelta(hours=6),
    )

    page = client.get(
        f"/staff/patients?q=Combo&status=ACTIVE&campaign_id=1"
        f"&start={ANCHOR_DAY.isoformat()}&end={ANCHOR_DAY.isoformat()}"
    )
    assert "Combo In Range Patient" in page.text
    assert "Combo Wrong Day Patient" not in page.text


def test_admin_dashboard_analytics_apply_the_same_local_day_rule_as_staff_list(client):
    """Requirement: admin and staff date-filter semantics must stay consistent."""
    response = client.post("/patients/register", data={
        "full_name": "Admin Consistency Patient", "mobile": "9500000006", "campaign_id": "1",
        "offer_id": "1", "beneficiary_category": "CGHS", "consent_given": "true",
    }, follow_redirects=False)
    assert response.status_code == 303
    db = SessionLocal()
    try:
        coupon = db.query(PatientOffer).filter(PatientOffer.patient.has(full_name="Admin Consistency Patient")).one()
        coupon.created_at = clinic_local_day_start_utc(ANCHOR_DAY) - timedelta(seconds=1)
        coupon_id = coupon.id
        db.commit()
    finally:
        db.close()

    db = SessionLocal()
    try:
        earlier_day_summary = dashboard_summary(db, start=ANCHOR_DAY - timedelta(days=1), end=ANCHOR_DAY - timedelta(days=1))
        anchor_day_summary = dashboard_summary(db, start=ANCHOR_DAY, end=ANCHOR_DAY)
    finally:
        db.close()

    assert earlier_day_summary["issued"] == 1
    assert anchor_day_summary["issued"] == 0
