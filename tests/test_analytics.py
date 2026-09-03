from datetime import timedelta

from app.audit_service import audit
from app.auth import password_hasher
from app.database import SessionLocal
from app.models import PatientOffer, StaffUser
from app.services.analytics_service import daily_time_series, staff_performance
from app.time_utils import utc_now


def _register(client, name: str, mobile: str):
    response = client.post("/patients/register", data={
        "full_name": name, "mobile": mobile, "campaign_id": "1",
        "offer_id": "1", "consent_given": "true",
    })
    assert response.status_code == 200


def test_time_series_uses_grouped_registration_and_redemption_dates(client):
    _register(client, "Analytics One", "9010000001")
    _register(client, "Analytics Two", "9010000002")
    now = utc_now()
    db = SessionLocal()
    try:
        first, second = db.query(PatientOffer).order_by(PatientOffer.id).all()
        first.created_at = now - timedelta(days=1)
        second.created_at = now
        first.status = "REDEEMED"
        first.redeemed_at = now
        db.commit()

        series = daily_time_series(db, start=(now - timedelta(days=1)).date(), end=now.date())
        registrations = {row["day"]: row["count"] for row in series["registrations"]}
        redemptions = {row["day"]: row["count"] for row in series["redemptions"]}
        assert registrations[str((now - timedelta(days=1)).date())] == 1
        assert registrations[str(now.date())] == 1
        assert redemptions[str(now.date())] == 1
    finally:
        db.close()


def test_staff_performance_aggregates_audit_events_by_username(client):
    db = SessionLocal()
    try:
        first = StaffUser(username="analytics-one", password_hash=password_hasher.hash("password"), role="staff")
        second = StaffUser(username="analytics-two", password_hash=password_hasher.hash("password"), role="staff")
        db.add_all([first, second])
        db.flush()
        audit(db, "analytics-one", "PATIENT_REGISTERED")
        audit(db, "analytics-one", "PATIENT_REGISTERED")
        audit(db, "analytics-one", "QR_REDEEMED")
        audit(db, "analytics-two", "QR_REDEEMED")
        db.commit()

        rows = {row["username"]: row for row in staff_performance(db)}
        assert rows["analytics-one"]["registrations"] == 2
        assert rows["analytics-one"]["redemptions"] == 1
        assert rows["analytics-two"]["registrations"] == 0
        assert rows["analytics-two"]["redemptions"] == 1
    finally:
        db.close()


def test_admin_dashboard_and_csv_exports_are_available_to_admin_only(client):
    _register(client, "Export Patient", "9010000003")
    dashboard = client.get("/admin/dashboard")
    assert dashboard.status_code == 200
    assert 'id="analytics-chart"' in dashboard.text
    campaign_csv = client.get("/admin/reports/campaigns.csv")
    patient_csv = client.get("/admin/reports/patients.csv")
    assert campaign_csv.status_code == 200 and "Campaign" in campaign_csv.text
    assert patient_csv.status_code == 200 and "Export Patient" in patient_csv.text

    db = SessionLocal()
    try:
        db.add(StaffUser(username="analytics-staff", password_hash=password_hasher.hash("password"), role="staff"))
        db.commit()
    finally:
        db.close()
    client.post("/logout")
    response = client.post("/staff/login", data={"username": "analytics-staff", "password": "password"}, follow_redirects=False)
    assert response.status_code == 303
    assert client.get("/admin/reports/patients.csv", follow_redirects=False).status_code == 403
