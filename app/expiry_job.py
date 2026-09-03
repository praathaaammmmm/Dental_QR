"""Cron entry point: run once from the deployment scheduler or private worker."""
import logging

from .database import SessionLocal
from .expiry_service import run_expiry_sweep


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    db = SessionLocal()
    try:
        result = run_expiry_sweep(db)
        logging.getLogger(__name__).info("Expiry sweep complete: %s", result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
