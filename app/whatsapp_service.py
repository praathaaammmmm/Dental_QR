from urllib.parse import quote

def prepare_whatsapp(patient, coupon):
    # Official API can be added later. Prototype uses a prefilled deep link.
    phone = "".join(ch for ch in (patient.mobile or "") if ch.isdigit())
    message = (
        f"Smriti Raj Dentistry - Complimentary Offer\n\n"
        f"Patient: {patient.full_name}\n"
        f"Offer: {coupon.offer.name}\n"
        f"QR ID: {coupon.coupon_uid}\n"
        f"Valid until: {coupon.expires_at.strftime('%d %B %Y')}\n"
        "One-time use only. Please present this QR at the clinic."
    )
    return f"https://wa.me/{phone}?text={quote(message)}"
