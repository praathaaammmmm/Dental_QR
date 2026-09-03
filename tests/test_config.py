import pytest

from app import config


def test_production_rejects_insecure_runtime(monkeypatch):
    monkeypatch.setattr(config, "APP_ENV", "production")
    monkeypatch.setattr(config, "CLINIC_PASSWORD_HASH", "$argon2id$configured")
    monkeypatch.setattr(config, "SESSION_SECRET_KEY", "x" * 32)
    monkeypatch.setattr(config, "SESSION_HTTPS_ONLY", False)
    monkeypatch.setattr(config, "DATABASE_URL", "sqlite:///unsafe.db")
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "http://unsafe.example")

    with pytest.raises(RuntimeError) as error:
        config.validate_security_config()

    message = str(error.value)
    assert "SESSION_HTTPS_ONLY" in message
    assert "PostgreSQL" in message
    assert "HTTPS" in message


def test_test_environment_accepts_sqlite(monkeypatch):
    monkeypatch.setattr(config, "APP_ENV", "test")
    monkeypatch.setattr(config, "CLINIC_PASSWORD_HASH", "$argon2id$configured")
    monkeypatch.setattr(config, "SESSION_SECRET_KEY", "x" * 32)
    monkeypatch.setattr(config, "SESSION_HTTPS_ONLY", False)
    monkeypatch.setattr(config, "DATABASE_URL", "sqlite:///test.db")
    monkeypatch.setattr(config, "PUBLIC_BASE_URL", "http://127.0.0.1:8000")

    config.validate_security_config()
