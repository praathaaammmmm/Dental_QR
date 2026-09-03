"""Shared QR delivery workflow for admin and staff interfaces."""
import base64

from ..audit_service import audit
from ..config import HOSPITAL_NAME, QR_DIR
from ..models import DeliveryLog, Patient, PatientOffer
from ..n8n_service import trigger_delivery


def send_qr_delivery(db, patient: Patient, coupon: PatientOffer, channel: str, actor: str) -> dict:
    """Trigger the existing n8n delivery boundary and persist its delivery log."""
    recipient = patient.email if channel == "EMAIL" else patient.mobile
    if not recipient:
        raise ValueError("No email address" if channel == "EMAIL" else "No phone number")
    qr_path = QR_DIR / f"{coupon.coupon_uid}.png"
    qr_b64 = base64.b64encode(qr_path.read_bytes()).decode("ascii") if qr_path.exists() else None
    result = trigger_delivery({
        "event": "REGISTRATION_QR_DELIVERY",
        "channel": channel,
        "hospital": HOSPITAL_NAME,
        "registration_id": coupon.coupon_uid,
        "patient": {"name": patient.full_name, "email": patient.email, "phone": patient.mobile},
        "service": coupon.offer.name,
        "campaign": coupon.campaign.name if coupon.campaign else patient.campaign_name,
        "expires_at": coupon.expires_at.isoformat(),
        "qr_base64_png": qr_b64,
    })
    db.add(DeliveryLog(
        coupon_id=coupon.id, channel=channel, recipient=recipient,
        status=result["status"], n8n_workflow_id=result.get("workflow_id"),
        failure_reason=result.get("reason"),
    ))
    audit(db, actor, f"{channel}_DELIVERY_TRIGGERED", coupon.id, patient.id, {
        "recipient": recipient, "status": result["status"],
    })
    db.commit()
    return result
