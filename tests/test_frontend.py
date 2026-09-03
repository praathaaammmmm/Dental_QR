def test_login_uses_integrated_frontend_and_cursor(client):
    client.post("/logout")
    response = client.get("/login")
    assert response.status_code == 200
    assert "Clinic Staff Login" in response.text
    assert "/static/cursor.js" in response.text
    assert "threejs" not in response.text.lower()


def test_static_frontend_assets_are_served(client):
    for path in ("/static/style.css", "/static/cursor.css", "/static/cursor.js", "/static/portal.js"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.content


def test_authenticated_pages_share_integrated_layout(client):
    for path in ("/", "/patients", "/patients/register", "/offers", "/validate", "/redemptions", "/delivery"):
        response = client.get(path)
        assert response.status_code == 200
        assert "Dentistry Ops" in response.text
        assert "/static/cursor.js" in response.text


def test_integrated_frontend_uses_real_backend_forms(client):
    registration = client.get("/patients/register")
    assert 'name="full_name"' in registration.text
    assert 'name="offer_id"' in registration.text
    assert 'name="consent_given"' in registration.text
    scanner = client.get("/validate")
    assert 'action="/validate"' in scanner.text
    assert 'name="_csrf_token"' in scanner.text
