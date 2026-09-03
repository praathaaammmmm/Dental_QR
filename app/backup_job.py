"""Daily cron entry point for encrypted file-backed SQLite backups."""
import logging

from .backup_service import create_encrypted_sqlite_backup, sqlite_path_from_database_url
from .config import BACKUP_DIR, BACKUP_ENCRYPTION_KEY, BACKUP_RETENTION_DAYS, DATABASE_URL


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    result = create_encrypted_sqlite_backup(
        sqlite_path_from_database_url(DATABASE_URL), BACKUP_DIR,
        BACKUP_ENCRYPTION_KEY, BACKUP_RETENTION_DAYS,
    )
    logging.getLogger(__name__).info(
        "Encrypted SQLite backup complete: artifact=%s bytes=%s sha256=%s",
        result["path"].name, result["bytes"], result["sha256"],
    )


if __name__ == "__main__":
    main()
