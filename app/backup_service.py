"""Encrypted, SQLite-only backup creation for the local deployment."""
import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.engine import make_url


def sqlite_path_from_database_url(database_url: str) -> Path:
    url = make_url(database_url)
    if url.drivername != "sqlite" or not url.database or url.database == ":memory:":
        raise RuntimeError("Encrypted backup job supports a file-backed SQLite DATABASE_URL only.")
    return Path(url.database).resolve()


def _fernet(key: str) -> Fernet:
    if not key:
        raise RuntimeError("BACKUP_ENCRYPTION_KEY is required; refusing to create a plaintext backup.")
    try:
        return Fernet(key.encode("utf-8"))
    except (ValueError, TypeError) as exc:
        raise RuntimeError("BACKUP_ENCRYPTION_KEY must be a valid Fernet key.") from exc


def _prune_old_backups(backup_dir: Path, retention_days: int, now: datetime) -> None:
    cutoff = now.timestamp() - retention_days * 24 * 60 * 60
    for artifact in backup_dir.glob("*.sqlite3.fernet"):
        metadata = artifact.with_suffix(".json")
        try:
            recorded_at = datetime.fromisoformat(json.loads(metadata.read_text(encoding="utf-8"))["created_at"])
            created_at = recorded_at.timestamp()
        except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            created_at = artifact.stat().st_mtime
        if created_at < cutoff:
            artifact.unlink()
            if metadata.exists():
                metadata.unlink()


def create_encrypted_sqlite_backup(
    source_path: Path,
    backup_dir: Path,
    encryption_key: str,
    retention_days: int = 30,
    now: datetime | None = None,
) -> dict:
    """Snapshot SQLite in memory, encrypt it, then atomically store the artifact.

    No plaintext backup is written to the backup directory. The returned checksum
    is calculated over the encrypted bytes actually stored for restoration.
    """
    source_path = Path(source_path).resolve()
    if not source_path.is_file():
        raise RuntimeError(f"SQLite database not found: {source_path}")
    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")
    now = now or datetime.now(timezone.utc)
    cipher = _fernet(encryption_key)
    backup_dir = Path(backup_dir).resolve()
    backup_dir.mkdir(parents=True, exist_ok=True)

    source = sqlite3.connect(str(source_path))
    snapshot = sqlite3.connect(":memory:")
    try:
        source.backup(snapshot)
        encrypted = cipher.encrypt(snapshot.serialize())
    finally:
        snapshot.close()
        source.close()

    stamp = now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    artifact = backup_dir / f"smritiraj-{stamp}.sqlite3.fernet"
    temporary = artifact.with_suffix(".tmp")
    with temporary.open("wb") as handle:
        handle.write(encrypted)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, artifact)

    checksum = hashlib.sha256(encrypted).hexdigest()
    metadata = artifact.with_suffix(".json")
    metadata.write_text(json.dumps({
        "created_at": now.astimezone(timezone.utc).isoformat(),
        "artifact": artifact.name,
        "bytes": len(encrypted),
        "sha256": checksum,
        "result": "success",
    }, indent=2), encoding="utf-8")
    _prune_old_backups(backup_dir, retention_days, now)
    return {"path": artifact, "metadata_path": metadata, "bytes": len(encrypted), "sha256": checksum}


def verify_encrypted_artifact(artifact: Path, encryption_key: str) -> None:
    """Validate the key and artifact before a documented restore procedure."""
    try:
        _fernet(encryption_key).decrypt(Path(artifact).read_bytes())
    except InvalidToken as exc:
        raise RuntimeError("Encrypted backup cannot be decrypted with BACKUP_ENCRYPTION_KEY.") from exc
