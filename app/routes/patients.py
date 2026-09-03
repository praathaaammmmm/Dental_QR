import logging
from fastapi import APIRouter, Depends, Request, Form, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from ..auth import require_admin
from ..audit_service import audit
from ..models import Patient, PatientOffer, Offer, Campaign, AuditLog
from ..security import require_csrf
from ..time_utils import utc_now
from ..services.registration_service import RegistrationError, register_patient_offer
from ..services.delivery_service import send_qr_delivery

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/patients")
def patients(request: Request, q: str = Query("", max_length=100), status: str = "", offer_id: int | None = None):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        query = db.query(PatientOffer).join(Patient).join(Offer)
        if q:
            query = query.filter(or_(Patient.full_name.ilike(f"%{q}%"), Patient.mobile.ilike(f"%{q}%")))
        if status:
            query = query.filter(PatientOffer.status == status)
        if offer_id:
            query = query.filter(PatientOffer.offer_id == offer_id)
        rows = query.order_by(Patient.created_at.desc()).all()
        offers = db.query(Offer).all()
        return request.app.state.templates.TemplateResponse(request, "patients.html", {
            "request": request, "rows": rows, "offers": offers, "q": q, "status": status, "offer_id": offer_id
        })
    finally:
        db.close()

@router.get("/patients/register")
def register_page(request: Request):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        offers = db.query(Offer).order_by(Offer.id).all()
        campaigns = db.query(Campaign).filter(Campaign.status == "ACTIVE").order_by(Campaign.start_date.desc()).all()
        return request.app.state.templates.TemplateResponse(request, "register.html", {"request": request, "offers": offers, "campaigns": campaigns, "error": None})
    finally:
        db.close()

@router.post("/patients/register")
def register_patient(
    request: Request,
    full_name: str = Form(...),
    mobile: str = Form(...),
    email: str = Form(""),
    age: str = Form(""),
    gender: str = Form(""),
    city: str = Form(""),
    doctor_name: str = Form(""),
    campaign_name: str = Form(""),
    campaign_id: int | None = Form(None),
    offer_id: int = Form(...),
    consent_given: bool = Form(False),
    _csrf: None = Depends(require_csrf),
):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        coupon = register_patient_offer(
            db, full_name=full_name, mobile=mobile, email=email, age=age, gender=gender,
            city=city, doctor_name=doctor_name, campaign_name=campaign_name,
            campaign_id=campaign_id, offer_id=offer_id, consent_given=consent_given,
            actor=request.session.get("user", "admin"),
        )
        return RedirectResponse(f"/patients/{coupon.patient_id}", status_code=303)
    except RegistrationError as exc:
        offers = db.query(Offer).order_by(Offer.id).all()
        campaigns = db.query(Campaign).filter(Campaign.status == "ACTIVE").order_by(Campaign.start_date.desc()).all()
        return request.app.state.templates.TemplateResponse(request, "register.html", {"request": request, "offers": offers, "campaigns": campaigns, "error": str(exc)}, status_code=422)
    except Exception:
        logger.exception("Patient registration failed")
        db.rollback()
        offers = db.query(Offer).order_by(Offer.id).all()
        campaigns = db.query(Campaign).filter(Campaign.status == "ACTIVE").order_by(Campaign.start_date.desc()).all()
        return request.app.state.templates.TemplateResponse(request, "register.html", {"request": request, "offers": offers, "campaigns": campaigns, "error": "Registration could not be completed. Please try again."}, status_code=500)
    finally:
        db.close()
@router.get("/patients/{patient_id}")
def patient_detail(request: Request, patient_id: int):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        patient = db.get(Patient, patient_id)
        if not patient:
            return RedirectResponse("/patients", status_code=303)
        coupon = max(patient.offers, key=lambda item: item.created_at) if patient.offers else None
        events = db.query(AuditLog).filter(AuditLog.patient_id == patient.id).order_by(AuditLog.timestamp.desc()).all()
        return request.app.state.templates.TemplateResponse(request, "patient_detail.html", {"request": request, "patient": patient, "coupon": coupon, "events": events})
    finally:
        db.close()

@router.post("/patients/{patient_id}/cancel")
def cancel_coupon(
    request: Request,
    patient_id: int,
    reason: str = Form(..., min_length=3, max_length=255),
    _csrf: None = Depends(require_csrf),
):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        patient = db.get(Patient, patient_id)
        if not patient or not patient.offers:
            return RedirectResponse("/patients", status_code=303)
        coupon = max(patient.offers, key=lambda item: item.created_at)
        if coupon.status != "ACTIVE":
            return RedirectResponse(f"/patients/{patient_id}?message=Only active offers can be cancelled", status_code=303)
        now = utc_now()
        coupon.status = "CANCELLED"
        coupon.cancelled_at = now
        coupon.cancelled_by = request.session.get("user", "admin")
        coupon.cancellation_reason = " ".join(reason.split())
        audit(db, coupon.cancelled_by, "QR_CANCELLED", coupon.id, patient.id, {"reason": coupon.cancellation_reason})
        db.commit()
        return RedirectResponse(f"/patients/{patient_id}?message=Offer cancelled", status_code=303)
    finally:
        db.close()

@router.post("/patients/{patient_id}/delivery/email")
def send_email(request: Request, patient_id: int, _csrf: None = Depends(require_csrf)):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        patient = db.get(Patient, patient_id)
        coupon = max(patient.offers, key=lambda item: item.created_at) if patient and patient.offers else None
        if not coupon:
            return RedirectResponse(f"/patients/{patient_id}?message=No active registration", status_code=303)
        try:
            result = send_qr_delivery(db, patient, coupon, "EMAIL", request.session.get("user", "admin"))
        except ValueError as exc:
            return RedirectResponse(f"/patients/{patient_id}?message={exc}", status_code=303)
        return RedirectResponse(f"/patients/{patient_id}?message=Email delivery {result['status'].lower()}", status_code=303)
    finally:
        db.close()

@router.post("/patients/{patient_id}/delivery/whatsapp")
def whatsapp(request: Request, patient_id: int, _csrf: None = Depends(require_csrf)):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        patient = db.get(Patient, patient_id)
        coupon = max(patient.offers, key=lambda item: item.created_at) if patient and patient.offers else None
        if not coupon:
            return RedirectResponse(f"/patients/{patient_id}?message=No active registration", status_code=303)
        try:
            result = send_qr_delivery(db, patient, coupon, "WHATSAPP", request.session.get("user", "admin"))
        except ValueError as exc:
            return RedirectResponse(f"/patients/{patient_id}?message={exc}", status_code=303)
        return RedirectResponse(f"/patients/{patient_id}?message=WhatsApp delivery {result['status'].lower()}", status_code=303)
    finally:
        db.close()
