from app.auth import password_hasher
from app.database import SessionLocal
from app.models import AuditLog, StaffUser
from app.routes.auth import _attempts
from tests.test_staff_interface import _create_staff, _login_as_staff


def test_removing_staff_revokes_access_and_hides_from_active_list(client):
    staff_id = _create_staff(username="removable-staff", password="removable-password")

    response = client.post(f"/admin/staff/{staff_id}/remove", follow_redirects=False)
    assert response.status_code == 303

    db = SessionLocal()
    try:
        user = db.get(StaffUser, staff_id)
        assert user.active is False
        assert user.removed_at is not None
    finally:
        db.close()

    listing = client.get("/admin/staff").text
    assert "removable-staff" not in listing


def test_login_is_blocked_after_removal(client):
    staff_id = _create_staff(username="blocked-staff", password="blocked-password")
    client.post(f"/admin/staff/{staff_id}/remove")

    client.post("/logout")
    _attempts.clear()
    response = client.post(
        "/login",
        data={"username": "blocked-staff", "password": "blocked-password"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "Invalid username or password" in response.text

    # Log back in as admin for any subsequent assertions using `client`.
    client.post("/login", data={"username": "smritiraj-clinic", "password": "test-password"})


def test_removal_preserves_prior_audit_history(client):
    _login_as_staff(client)
    client.post("/staff/register", data={
        "full_name": "Audited Staff Patient", "mobile": "9888800009",
        "campaign_id": "1", "offer_id": "1", "beneficiary_category": "CGHS", "consent_given": "true",
    })

    db = SessionLocal()
    try:
        staff_user_id = db.query(StaffUser).filter(StaffUser.username == "staff-user").one().id
        prior_audit_count = db.query(AuditLog).filter(AuditLog.user == "staff-user").count()
        assert prior_audit_count > 0
    finally:
        db.close()

    client.post("/logout")
    client.post("/login", data={"username": "smritiraj-clinic", "password": "test-password"})
    client.post(f"/admin/staff/{staff_user_id}/remove")

    db = SessionLocal()
    try:
        remaining_audit_count = db.query(AuditLog).filter(AuditLog.user == "staff-user").count()
        assert remaining_audit_count == prior_audit_count
        assert db.query(AuditLog).filter(
            AuditLog.action == "STAFF_ACCOUNT_REMOVED",
        ).count() == 1
    finally:
        db.close()


def test_admin_account_cannot_be_removed_via_staff_route(client):
    db = SessionLocal()
    try:
        admin_row = StaffUser(
            username="not-a-real-admin-row", password_hash=password_hasher.hash("irrelevant-password"),
            role="admin", active=True,
        )
        db.add(admin_row)
        db.commit()
        admin_row_id = admin_row.id
    finally:
        db.close()

    client.post(f"/admin/staff/{admin_row_id}/remove")

    db = SessionLocal()
    try:
        admin_row = db.get(StaffUser, admin_row_id)
        assert admin_row.active is True
        assert admin_row.removed_at is None
    finally:
        db.close()
