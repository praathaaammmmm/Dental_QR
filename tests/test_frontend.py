def test_login_uses_integrated_frontend_and_cursor(client):
    client.post("/logout")
    response = client.get("/login")
    assert response.status_code == 200
    assert "Clinic Login" in response.text
    assert "/static/cursor.js" in response.text
    assert "threejs" not in response.text.lower()


def test_static_frontend_assets_are_served(client):
    for path in ("/static/style.css", "/static/cursor.css", "/static/cursor.js", "/static/portal.js", "/static/img/nabh-accredited.png"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.content


def test_authenticated_pages_share_integrated_layout(client):
    # The decorative custom-cursor effect and the top-header's diamond/help/avatar
    # icons are login-page-only flourishes; the authenticated CRM chrome deliberately
    # drops them (kept: sidebar navigation, sign-out, section title).
    for path in ("/", "/patients", "/patients/register", "/offers", "/validate", "/redemptions", "/delivery"):
        response = client.get(path)
        assert response.status_code == 200
        assert "Dentistry Ops" in response.text
        assert "/static/cursor.js" not in response.text
        assert "/static/cursor.css" not in response.text
        assert '/static/img/nabh-accredited.png' in response.text
        assert 'alt="NABH Accredited – Patient Safety &amp; Quality of Care"' in response.text


def test_authenticated_header_drops_decorative_icons_but_keeps_navigation(client):
    response = client.get("/admin/dashboard")
    assert response.status_code == 200
    text = response.text
    assert 'class="staff-avatar"' not in text
    assert '<span aria-hidden="true">♢</span>' not in text
    assert '<span aria-hidden="true">?</span>' not in text
    # The top-header bar itself (section title) stays; only the icon cluster is gone --
    # no leftover empty wrapper div in its place.
    assert '<header class="top-header">' in text
    assert '<header class="top-header"><strong>' in text
    # Sidebar navigation and sign-out remain fully available.
    assert 'aside class="sidebar"' in text
    assert 'action="/logout"' in text or 'action="/staff/logout"' in text
    assert 'Sign out' in text


def test_integrated_frontend_uses_real_backend_forms(client):
    registration = client.get("/patients/register")
    assert 'name="full_name"' in registration.text
    assert 'name="offer_id"' in registration.text
    assert 'name="consent_given"' in registration.text
    scanner = client.get("/validate")
    assert 'action="/validate"' in scanner.text
    assert 'name="_csrf_token"' in scanner.text
