def test_post_without_csrf_is_rejected(client):
    response = client.post("/logout", include_csrf=False)
    assert response.status_code == 403


def test_post_with_wrong_csrf_is_rejected(client):
    response = client.post("/logout", include_csrf=False, data={"_csrf_token": "wrong"})
    assert response.status_code == 403


def test_security_headers_are_present(client):
    response = client.get("/health")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"


def test_unknown_host_is_rejected(client):
    response = client.get("/health", headers={"host": "attacker.example"})
    assert response.status_code == 400


def test_registration_rejects_invalid_contact_data(client):
    response = client.post(
        "/patients/register",
        data={"full_name": "Test Patient", "mobile": "12", "email": "not-an-email", "offer_id": "1"},
    )
    assert response.status_code == 422
    assert "Mobile" in response.text or "Email" in response.text


def test_registration_does_not_expose_internal_error(client, monkeypatch):
    from app.routes import patients

    def fail_generation(*_args, **_kwargs):
        raise RuntimeError("SECRET INTERNAL FAILURE")

    monkeypatch.setattr(patients, "generate_qr", fail_generation)
    response = client.post(
        "/patients/register",
        data={"full_name": "Test Patient", "mobile": "9999999999", "offer_id": "1", "consent_given": "true"},
    )
    assert response.status_code == 500
    assert "Registration could not be completed" in response.text
    assert "SECRET INTERNAL FAILURE" not in response.text
