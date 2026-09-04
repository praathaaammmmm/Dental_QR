from app.auth import password_hasher
from app.database import SessionLocal
from app.models import AuditLog, Patient, StaffUser
from app.routes.auth import _attempts


def _create_staff(username="staff-user", password="staff-password"):
    db = SessionLocal()
    try:
        user = StaffUser(
            username=username,
            password_hash=password_hasher.hash(password),
            role="staff",
            active=True,
        )
        db.add(user)
        db.commit()
        return user.id
    finally:
        db.close()


def _login_as_staff(client):
    _create_staff()
    _attempts.clear()
    client.post("/logout")
    response = client.post(
        "/login",
        data={"username": "staff-user", "password": "staff-password"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/staff/home"


def test_staff_session_is_rejected_from_admin_urls(client):
    """Hidden admin navigation is not the authorization boundary."""
    _login_as_staff(client)
    response = client.get("/admin/dashboard", follow_redirects=False)
    assert response.status_code == 403
    response = client.get("/admin/campaigns", follow_redirects=False)
    assert response.status_code == 403


def test_staff_registration_uses_active_campaign_and_audits_actor(client):
    _login_as_staff(client)
    response = client.post(
        "/staff/register",
        data={
            "full_name": "Staff Registered Patient", "mobile": "9876543210",
            "campaign_id": "1", "offer_id": "1", "beneficiary_category": "ECHS", "consent_given": "true",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/staff/patients/")
    db = SessionLocal()
    try:
        patient = db.query(Patient).filter_by(full_name="Staff Registered Patient").one()
        assert patient.offers[0].campaign_id == 1
        event = db.query(AuditLog).filter_by(patient_id=patient.id, action="PATIENT_REGISTERED").one()
        assert event.user == "staff-user"
    finally:
        db.close()
