from fastapi import APIRouter, Request, Header, HTTPException

from ..auth import require_auth
from ..models import DeliveryLog, PatientOffer
from ..config import N8N_WEBHOOK_SECRET

router = APIRouter()

@router.get("/redemptions")
def redemptions(request: Request):
    guard = require_auth(request)
    if guard:
        return guard
    db = request.app.state.db()
    try:
        rows = db.query(PatientOffer).filter(PatientOffer.status == "REDEEMED").order_by(PatientOffer.redeemed_at.desc()).all()
        return request.app.state.templates.TemplateResponse(request, "redemptions.html", {"request": request, "rows": rows})
    finally:
        db.close()

@router.get("/delivery")
def delivery(request: Request):
    guard = require_auth(request)
    if guard:
        return guard
    db = request.app.state.db()
    try:
        rows = db.query(DeliveryLog, PatientOffer).join(PatientOffer, DeliveryLog.coupon_id == PatientOffer.id).order_by(DeliveryLog.sent_at.desc()).all()
        return request.app.state.templates.TemplateResponse(request, "delivery.html", {"request": request, "rows": rows})
    finally:
        db.close()

@router.post("/webhooks/n8n/delivery")
def n8n_delivery_webhook(request: Request, payload: dict, x_n8n_webhook_secret: str = Header(default="")):
    """Receive delivery updates from n8n; never expose this endpoint without a secret."""
    if not N8N_WEBHOOK_SECRET or x_n8n_webhook_secret != N8N_WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")
    workflow_id = payload.get("workflow_id")
    registration_id = payload.get("registration_id")
    status = str(payload.get("status", "")).upper()
    if status not in {"PENDING", "SENT", "DELIVERED", "FAILED"}:
        raise HTTPException(status_code=400, detail="Invalid delivery status")
    db = request.app.state.db()
    try:
        query = db.query(DeliveryLog)
        if workflow_id:
            query = query.filter(DeliveryLog.n8n_workflow_id == workflow_id)
        elif registration_id:
            query = query.join(PatientOffer).filter(PatientOffer.coupon_uid == registration_id)
        else:
            raise HTTPException(status_code=400, detail="Missing delivery reference")
        log = query.order_by(DeliveryLog.sent_at.desc()).first()
        if not log:
            raise HTTPException(status_code=404, detail="Delivery record not found")
        log.status = status
        log.provider_message_id = payload.get("provider_message_id") or log.provider_message_id
        log.failure_reason = payload.get("failure_reason") if status == "FAILED" else None
        if workflow_id:
            log.n8n_workflow_id = workflow_id
        db.commit()
        return {"status": "ok"}
    finally:
        db.close()
