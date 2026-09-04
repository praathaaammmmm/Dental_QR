"""Scheduled delivery dispatch: sends queued QR notifications via n8n.

Run by ``python -m app.delivery_job`` from one external scheduler/worker only, every
1 minute in production-like environments. FastAPI request paths never call n8n
directly — this job is the only place outbound delivery HTTP calls happen.
"""
import logging

from .database import SessionLocal
from .services.delivery_service import dispatch_pending_deliveries, maybe_retry_failed_intents


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    db = SessionLocal()
    try:
        dispatch_result = dispatch_pending_deliveries(db)
        retried = maybe_retry_failed_intents(db)
        logger.info("Delivery dispatch complete: %s, retries_created=%s", dispatch_result, retried)
    finally:
        db.close()


if __name__ == "__main__":
    main()
