from urllib.parse import quote
from .config import SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM

def prepare_email(patient, coupon, qr_path):
    # Prototype mode: no external provider is required. Return/log a ready-to-send payload.
    return {
        "recipient": patient.email,
        "subject": "Your Complimentary Offer from Smriti Raj Dentistry",
        "body": (
            f"Dear {patient.full_name},\n\n"
            f"You have received: {coupon.offer.name}.\n"
            f"QR ID: {coupon.coupon_uid}\n"
            f"Valid until: {coupon.expires_at.strftime('%d %B %Y')}\n"
            f"This offer is one-time use only.\n\n"
            "Please present the QR at Smriti Raj Dentistry."
        ),
        "qr_path": str(qr_path),
        "smtp_configured": bool(SMTP_HOST and SMTP_USERNAME and SMTP_PASSWORD and SMTP_FROM),
    }
