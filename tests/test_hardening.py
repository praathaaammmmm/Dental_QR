import hashlib
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet

from app.auth import password_hasher
from app.backup_service import create_encrypted_sqlite_backup, verify_encrypted_artifact
from app.database import SessionLocal
from app.models import StaffUser
from app.security import _attempts


def _login_staff(client):
    db = SessionLocal()
    try:
        db.add(StaffUser(username="hardening-staff", password_hash=password_hasher.hash("test-password"), role="staff"))
        db.commit()
    finally:
        db.close()
    client.post("/logout")
    response = client.post("/staff/login", data={"username": "hardening-staff", "password": "test-password"}, follow_redirects=False)
    assert response.status_code == 303


def test_staff_validation_rate_limit_uses_a_separate_scoped_bucket(client, monkeypatch):
    from app.routes import staff as staff_routes

    _attempts.clear()
    _login_staff(client)
    monkeypatch.setattr(staff_routes, "VALIDATION_RATE_LIMIT_ATTEMPTS", 2)
    monkeypatch.setattr(staff_routes, "VALIDATION_RATE_LIMIT_WINDOW_SECONDS", 60)

    assert client.post("/staff/validate", data={"token": "SRD-NOT-REAL"}).status_code == 200
    assert client.post("/staff/validate", data={"token": "SRD-NOT-REAL"}).status_code == 200
    limited = client.post("/staff/validate", data={"token": "SRD-NOT-REAL"})
    assert limited.status_code == 429
    assert "Too many validation attempts" in limited.text


def test_encrypted_sqlite_backup_checksum_covers_stored_artifact(tmp_path):
    source = tmp_path / "source.db"
    connection = sqlite3.connect(source)
    connection.execute("create table patient_data (id integer primary key, value text)")
    connection.execute("insert into patient_data (value) values ('protected')")
    connection.commit()
    connection.close()

    key = Fernet.generate_key().decode()
    result = create_encrypted_sqlite_backup(source, tmp_path / "backups", key, now=datetime(2026, 9, 4, tzinfo=timezone.utc))
    encrypted_bytes = result["path"].read_bytes()
    assert result["sha256"] == hashlib.sha256(encrypted_bytes).hexdigest()
    assert not encrypted_bytes.startswith(b"SQLite format 3")
    assert Fernet(key.encode()).decrypt(encrypted_bytes).startswith(b"SQLite format 3")
    verify_encrypted_artifact(result["path"], key)


def test_backup_refuses_missing_key_and_prunes_retention(tmp_path):
    source = tmp_path / "source.db"
    sqlite3.connect(source).close()
    with pytest.raises(RuntimeError, match="BACKUP_ENCRYPTION_KEY"):
        create_encrypted_sqlite_backup(source, tmp_path / "backups", "")

    key = Fernet.generate_key().decode()
    backup_dir = tmp_path / "backups"
    create_encrypted_sqlite_backup(source, backup_dir, key, retention_days=1, now=datetime(2026, 9, 1, tzinfo=timezone.utc))
    create_encrypted_sqlite_backup(source, backup_dir, key, retention_days=1, now=datetime(2026, 9, 4, tzinfo=timezone.utc))
    assert len(list(backup_dir.glob("*.sqlite3.fernet"))) == 1
