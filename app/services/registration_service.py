"""Business workflow for legacy PatientOffer registration creation."""
from datetime import datetime, timedelta

from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit_service import audit
from ..models import Campaign, Offer, Patient, PatientOffer
from ..qr_service import expiry_for, generate_qr, new_uid, token_for, token_hash
from .delivery_service import queue_registration_deliveries
from ..schemas import PatientCreate
from ..time_utils import utc_now

CONSENT_VERSION = "2026-09-02"


class RegistrationError(Exception):
    """A safe, user-actionable registration failure."""


class CampaignUnavailableError(RegistrationError):
    pass


class OfferUnavailableError(RegistrationError):
    pass


class DuplicateRegistrationError(RegistrationError):
    pass


def sunday_for(moment: datetime):
    return (moment - timedelta(days=(moment.weekday() + 1) % 7)).date()


def _validated_form(**values) -> PatientCreate:
    try:
        return PatientCreate(**values)
    except ValidationError as exc:
        first_error = exc.errors(include_url=False)[0]
        field = str(first_error.get("loc", ["field"])[-1]).replace("_", " ").title()
        raise RegistrationError(f"{field}: {first_error['msg']}") from None


def register_patient_offer(
    db: Session,
    *,
    full_name: str,
    mobile: str,
    email: str,
    age: str,
    gender: str,
    city: str,
    doctor_name: str,
    campaign_name: str,
    campaign_id: int | None,
    offer_id: int,
    beneficiary_category: str,
    consent_given: bool,
    actor: str,
) -> PatientOffer:
    """Create a patient and its legacy PatientOffer in one transaction.

    This deliberately preserves the existing weekly duplicate rule and QR/audit
    behavior. Notification delivery is queued durably (PREPARED DeliveryLog rows) in
    the same transaction; actual sending happens later via the delivery dispatcher.
    """
    form = _validated_form(
        full_name=full_name,
        mobile=mobile,
        email=email or None,
        age=age or None,
        gender=gender or None,
        city=city or None,
        doctor_name=doctor_name or None,
        campaign_name=campaign_name or None,
        offer_id=offer_id,
        beneficiary_category=beneficiary_category,
        consent_given=consent_given,
    )
    try:
        offer = db.get(Offer, form.offer_id)
        if not offer:
            raise OfferUnavailableError("Please select a valid offer.")
        if not form.consent_given:
            raise RegistrationError("Patient consent is required before registration.")

        now = utc_now()
        campaign = db.get(Campaign, campaign_id) if campaign_id else None
        if not campaign or campaign.status != "ACTIVE":
            raise CampaignUnavailableError("Please select an active campaign.")
        if not (campaign.start_date <= now.date() <= campaign.end_date):
            raise CampaignUnavailableError("The selected campaign is not active for today's date.")
        if campaign.offers and offer.id not in {item.id for item in campaign.offers}:
            raise OfferUnavailableError("The selected service is not part of this campaign.")

        registration_week = sunday_for(now)
        duplicate = db.query(Patient).filter(
            Patient.mobile == form.mobile,
            Patient.registration_week == registration_week,
        ).first()
        if duplicate:
            raise DuplicateRegistrationError(
                "This mobile number is already registered for the current Sunday-to-Saturday campaign week."
            )

        patient = Patient(
            patient_uid=new_uid("PAT"), full_name=form.full_name, mobile=form.mobile,
            email=str(form.email) if form.email else None, age=form.age, gender=form.gender,
            city=form.city, doctor_name=form.doctor_name, campaign_name=form.campaign_name,
            registration_week=registration_week, consent_given=True,
            consent_version=CONSENT_VERSION, consented_at=now, created_at=now,
        )
        db.add(patient)
        db.flush()

        coupon_uid = new_uid("SRD")
        token = token_for(coupon_uid)
        coupon = PatientOffer(
            coupon_uid=coupon_uid, patient_id=patient.id, offer_id=offer.id,
            campaign_id=campaign.id, secure_token_hash=token_hash(token),
            created_at=now, expires_at=expiry_for(now), status="ACTIVE",
            beneficiary_category=form.beneficiary_category,
        )
        db.add(coupon)
        db.flush()
        generate_qr(token, coupon.coupon_uid)
        audit(db, actor, "PATIENT_REGISTERED", coupon.id, patient.id, {
            "offer": offer.name, "registration_week": str(registration_week),
            "consent_version": CONSENT_VERSION, "beneficiary_category": form.beneficiary_category,
        })
        audit(db, "admin", "QR_GENERATED", coupon.id, patient.id)
        # Durable outbox write only — no network call happens here, so a slow or unavailable
        # n8n endpoint can never block or roll back this registration. The dispatcher
        # (app/delivery_job.py) sends these PREPARED intents separately.
        queue_registration_deliveries(db, patient, coupon, actor)
        db.commit()
        return coupon
    except IntegrityError as exc:
        db.rollback()
        raise DuplicateRegistrationError(
            "This mobile number is already registered for the current campaign week."
        ) from exc
    except Exception:
        db.rollback()
        raise