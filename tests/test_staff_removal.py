from app.auth import password_hasher
from app.database import SessionLocal
from app.models import AuditLog, StaffUser
from app.routes.auth import _attempts
from app.time_utils import utc_now
from tests.test_staff_interface import _create_staff, _login_as_staff


def test_staff_row_actions_are_grouped_compactly_and_no_longer_inline_styled(client):
    """Deactivate/Remove used to be two separate forms joined only by a literal space and
    an ad hoc `style="display:inline-block"` on each. They must now share one compact,
    right-aligned action group (styled entirely from style.css, matching the app's CSP)."""
    staff_id = _create_staff(username="button-layout-staff", password="button-layout-password")
    listing = client.get("/admin/staff").text
    group_start = listing.index(f'action="/admin/staff/{staff_id}/toggle"')
    group_start = listing.rindex('<div class="staff-actions">', 0, group_start)
    group_end = listing.index("</div>", listing.index(f'action="/admin/staff/{staff_id}/remove"', group_start))
    group_chunk = listing[group_start:group_end]
    assert f'action="/admin/staff/{staff_id}/toggle"' in group_chunk
    assert f'action="/admin/staff/{staff_id}/remove"' in group_chunk
    assert "style=" not in group_chunk

    stylesheet = client.get("/static/style.css").text
    assert ".staff-actions{display:flex" in stylesheet
    assert "justify-content:flex-end" in stylesheet
    assert "flex-wrap:wrap" in stylesheet


def test_staff_page_renders_after_removal_with_mixed_staff_states(client):
    """Regression test for a 500 on GET /admin/staff: the page must render for an
    authenticated admin regardless of whether any staff accounts are active, merely
    deactivated (toggled off but not removed), or removed/archived."""
    active_id = _create_staff(username="mixed-active-staff", password="mixed-active-password")
    deactivated_id = _create_staff(username="mixed-deactivated-staff", password="mixed-deactivated-password")
    removed_id = _create_staff(username="mixed-removed-staff", password="mixed-removed-password")

    client.post(f"/admin/staff/{deactivated_id}/toggle")
    client.post(f"/admin/staff/{removed_id}/remove")

    response = client.get("/admin/staff")
    assert response.status_code == 200
    assert "mixed-active-staff" in response.text
    assert "mixed-deactivated-staff" in response.text
    assert "mixed-removed-staff" not in response.text


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


def test_creating_a_removed_username_offers_restore_instead_of_a_duplicate(client):
    staff_id = _create_staff(username="reusable-username", password="original-password")
    client.post(f"/admin/staff/{staff_id}/remove")

    response = client.post("/admin/staff", data={
        "username": "reusable-username", "password": "brand-new-password-123",
    }, follow_redirects=False)
    assert response.status_code == 303
    assert f"restore_id={staff_id}" in response.headers["location"]

    db = SessionLocal()
    try:
        assert db.query(StaffUser).filter(StaffUser.username == "reusable-username").count() == 1
        still_removed = db.get(StaffUser, staff_id)
        assert still_removed.removed_at is not None
        assert still_removed.active is False
    finally:
        db.close()

    listing = client.get(response.headers["location"]).text
    assert "Restore staff account" in listing
    assert "reusable-username" in listing
    assert f'action="/admin/staff/{staff_id}/restore"' in listing


def test_restoring_removed_staff_reactivates_with_new_password_and_login_works(client):
    staff_id = _create_staff(username="restorable-staff", password="old-password-value")
    client.post(f"/admin/staff/{staff_id}/remove")

    response = client.post(f"/admin/staff/{staff_id}/restore", data={
        "password": "brand-new-restored-password",
    }, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/admin/staff")

    db = SessionLocal()
    try:
        user = db.get(StaffUser, staff_id)
        assert user.active is True
        assert user.removed_at is None
    finally:
        db.close()

    followed = client.get(response.headers["location"])
    assert "Staff account restored and access re-enabled." in followed.text

    client.post("/logout")
    _attempts.clear()
    login_with_old = client.post("/login", data={
        "username": "restorable-staff", "password": "old-password-value",
    }, follow_redirects=False)
    assert login_with_old.status_code == 200
    assert "Invalid username or password" in login_with_old.text

    login_with_new = client.post("/login", data={
        "username": "restorable-staff", "password": "brand-new-restored-password",
    }, follow_redirects=False)
    assert login_with_new.status_code == 303
    assert login_with_new.headers["location"] == "/staff/home"

    client.post("/login", data={"username": "smritiraj-clinic", "password": "test-password"})


def test_duplicate_active_username_is_still_rejected_not_offered_restore(client):
    _create_staff(username="already-active-staff", password="first-password-value")

    response = client.post("/admin/staff", data={
        "username": "already-active-staff", "password": "second-password-value",
    }, follow_redirects=False)
    assert response.status_code == 303
    assert "restore_id" not in response.headers["location"]

    followed = client.get(response.headers["location"])
    assert "already in use" in followed.text
    assert "Restore staff account" not in followed.text

    db = SessionLocal()
    try:
        assert db.query(StaffUser).filter(StaffUser.username == "already-active-staff").count() == 1
    finally:
        db.close()


def test_restore_preserves_prior_audit_history_and_writes_restored_event(client):
    _login_as_staff(client)
    client.post("/staff/register", data={
        "full_name": "Pre-Restore Audit Patient", "mobile": "9888800010",
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
    client.post(f"/admin/staff/{staff_user_id}/restore", data={"password": "post-restore-password-1"})

    db = SessionLocal()
    try:
        remaining_audit_count = db.query(AuditLog).filter(AuditLog.user == "staff-user").count()
        assert remaining_audit_count == prior_audit_count
        assert db.query(AuditLog).filter(AuditLog.action == "STAFF_ACCOUNT_RESTORED").count() == 1
        user = db.get(StaffUser, staff_user_id)
        assert user.active is True
        assert user.removed_at is None
    finally:
        db.close()


def test_admin_account_cannot_be_restored_via_staff_route(client):
    db = SessionLocal()
    try:
        admin_row = StaffUser(
            username="not-a-real-admin-row-2", password_hash=password_hasher.hash("irrelevant-password"),
            role="admin", active=True, removed_at=utc_now(),
        )
        db.add(admin_row)
        db.commit()
        admin_row_id = admin_row.id
    finally:
        db.close()

    client.post(f"/admin/staff/{admin_row_id}/restore", data={"password": "should-not-apply-12345"})

    db = SessionLocal()
    try:
        admin_row = db.get(StaffUser, admin_row_id)
        assert admin_row.removed_at is not None
    finally:
        db.close()
