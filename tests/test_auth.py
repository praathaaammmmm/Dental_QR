from app.routes.auth import _attempts


def test_login_rejects_wrong_credentials(client):
    client.post("/logout")
    response = client.post("/login", data={"username": "smritiraj-clinic", "password": "wrong-password"})
    assert response.status_code == 200
    assert "Invalid username or password" in response.text


def test_protected_page_requires_login(client):
    client.post("/logout")
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_valid_centralized_login_creates_session(client):
    client.post("/logout")
    response = client.post(
        "/login",
        data={"username": "smritiraj-clinic", "password": "test-password"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/dashboard"
    assert "srd_clinic_session=" in response.headers["set-cookie"]
    assert "httponly" in response.headers["set-cookie"].lower()


def test_login_is_rate_limited_after_repeated_failures(client):
    client.post("/logout")
    _attempts.clear()
    for _ in range(5):
        client.post("/login", data={"username": "smritiraj-clinic", "password": "wrong-password"})
    response = client.post("/login", data={"username": "smritiraj-clinic", "password": "wrong-password"})
    assert response.status_code == 429
    _attempts.clear()
