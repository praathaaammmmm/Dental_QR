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


def test_remove_control_is_a_csrf_protected_post_form_not_a_link(client):
    """The bug this guards against: if "Remove" ever regresses to a plain <a href> (or a
    form without a CSRF token), clicking it issues a GET, which 404s -- the whole point
    of a CSRF-protected POST action is that a bare navigation can never trigger it."""
    staff_id = _create_staff(username="form-shape-staff", password="form-shape-password")
    listing = client.get("/admin/staff").text
    assert f'<form method="post" action="/admin/staff/{staff_id}/remove"' in listing
    # The remove form must carry its own CSRF token, not rely on some other form's.
    remove_form_start = listing.index(f'action="/admin/staff/{staff_id}/remove"')
    remove_form_chunk = listing[remove_form_start:remove_form_start + 400]
    assert 'name="_csrf_token"' in remove_form_chunk
    assert f'<a href="/admin/staff/{staff_id}/remove"' not in listing


def test_get_on_the_remove_url_never_shows_raw_json_404(client):
    """Reproduces the reported bug directly: navigating (GET) to the POST-only remove
    URL must render a friendly page, never FastAPI's default `{"detail": "..."}` JSON."""
    staff_id = _create_staff(username="get-navigated-staff", password="get-navigated-password")

    response = client.get(f"/admin/staff/{staff_id}/remove")
    assert response.status_code == 405
    assert "application/json" not in response.headers.get("content-type", "")
    assert '{"detail"' not in response.text
    assert "text/html" in response.headers.get("content-type", "")

    # The GET must not have performed the removal as a side effect.
    db = SessionLocal()
    try:
        user = db.get(StaffUser, staff_id)
        assert user.active is True
        assert user.removed_at is None
    finally:
        db.close()


def test_unknown_admin_page_shows_friendly_404_not_raw_json(client):
    response = client.get("/admin/staff/999999/this-route-does-not-exist")
    assert response.status_code == 404
    assert '{"detail"' not in response.text
    assert "text/html" in response.headers.get("content-type", "")


def test_webhook_404_still_returns_json_unaffected_by_the_friendly_error_page(client):
    """The friendly-HTML-error handling must be scoped to browser pages only -- the n8n
    delivery webhook is a machine API and must keep its plain JSON error contract."""
    import os

    response = client.post(
        "/webhooks/n8n/delivery",
        json={"idempotency_key": "does-not-exist", "status": "SENT"},
        headers={"X-N8N-Webhook-Secret": os.environ["N8N_WEBHOOK_SECRET"]},
        include_csrf=False,
    )
    assert response.status_code == 404
    assert response.json()["detail"]


def test_successful_removal_redirects_to_staff_list_with_success_message(client):
    staff_id = _create_staff(username="redirect-staff", password="redirect-password")

    response = client.post(f"/admin/staff/{staff_id}/remove", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/admin/staff")

    followed = client.get(response.headers["location"])
    assert followed.status_code == 200
    assert "Staff account removed and access revoked." in followed.text


def test_repeat_removal_is_idempotent_and_causes_no_further_change(client):
    staff_id = _create_staff(username="repeat-removed-staff", password="repeat-removed-password")

    first = client.post(f"/admin/staff/{staff_id}/remove", follow_redirects=False)
    assert first.status_code == 303
    db = SessionLocal()
    try:
        removed_at_after_first = db.get(StaffUser, staff_id).removed_at
    finally:
        db.close()

    second = client.post(f"/admin/staff/{staff_id}/remove", follow_redirects=True)
    assert second.status_code == 200
    assert "already removed" in second.text.lower()

    db = SessionLocal()
    try:
        user = db.get(StaffUser, staff_id)
        assert user.active is False
        assert user.removed_at == removed_at_after_first
        assert db.query(AuditLog).filter(
            AuditLog.action == "STAFF_ACCOUNT_REMOVED", AuditLog.details.contains("repeat-removed-staff"),
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
