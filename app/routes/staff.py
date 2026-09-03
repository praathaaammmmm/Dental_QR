from datetime import date, timedelta

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_, select

from ..audit_service import audit
from ..auth import require_staff
from ..coupon_service import redeem_atomic, refresh_expiry
from ..models import AuditLog, Campaign, Offer, Patient, PatientOffer
from ..security import require_csrf
from ..services.delivery_service import send_qr_delivery
from ..services.registration_service import RegistrationError, register_patient_offer
from ..time_utils import utc_now
from .validation import find_coupon, result_for

router = APIRouter()


def _context(request: Request, **values):
    return {"request": request, "workspace": "staff", **values}


def _active_campaigns(db):
    today = utc_now().date()
    return db.query(Campaign).filter(
        Campaign.status == "ACTIVE", Campaign.start_date <= today, Campaign.end_date >= today,
    ).order_by(Campaign.start_date.desc()).all()


@router.get("/staff")
def staff_root():
    return RedirectResponse("/staff/home", status_code=303)


@router.get("/staff/home")
def staff_home(request: Request):
    guard = require_staff(request)
    if guard:
        return guard
    db = request.app.state.db()
    try:
        return request.app.state.templates.TemplateResponse(request, "staff_home.html", _context(
            request, campaigns=_active_campaigns(db),
            active_qrs=db.query(PatientOffer).filter(PatientOffer.status == "ACTIVE").count(),
        ))
    finally:
        db.close()


@router.get("/staff/register")
def register_page(request: Request):
    guard = require_staff(request)
    if guard:
        return guard
    db = request.app.state.db()
    try:
        return request.app.state.templates.TemplateResponse(request, "register.html", _context(
            request, offers=db.query(Offer).order_by(Offer.id).all(), campaigns=_active_campaigns(db), error=None,
            form_action="/staff/register", back_url="/staff/home",
        ))
    finally:
        db.close()


@router.post("/staff/register")
def register_patient(
    request: Request, full_name: str = Form(...), mobile: str = Form(...), email: str = Form(""),
    age: str = Form(""), gender: str = Form(""), city: str = Form(""), doctor_name: str = Form(""),
    campaign_name: str = Form(""), campaign_id: int | None = Form(None), offer_id: int = Form(...),
    consent_given: bool = Form(False), _csrf: None = Depends(require_csrf),
):
    guard = require_staff(request)
    if guard:
        return guard
    db = request.app.state.db()
    try:
        try:
            coupon = register_patient_offer(
                db, full_name=full_name, mobile=mobile, email=email, age=age, gender=gender, city=city,
                doctor_name=doctor_name, campaign_name=campaign_name, campaign_id=campaign_id, offer_id=offer_id,
                consent_given=consent_given, actor=request.session["user"],
            )
            return RedirectResponse(f"/staff/patients/{coupon.patient_id}", status_code=303)
        except RegistrationError as exc:
            error, status_code = str(exc), 422
        except Exception:
            db.rollback()
            error, status_code = "Registration could not be completed. Please try again.", 500
        return request.app.state.templates.TemplateResponse(request, "register.html", _context(
            request, offers=db.query(Offer).order_by(Offer.id).all(), campaigns=_active_campaigns(db), error=error,
            form_action="/staff/register", back_url="/staff/home",
        ), status_code=status_code)
    finally:
        db.close()


@router.get("/staff/patients")
def patients(
    request: Request, q: str = Query("", max_length=100), status: str = "", campaign_id: int | None = None,
    start: str = "", end: str = "",
):
    guard = require_staff(request)
    if guard:
        return guard
    db = request.app.state.db()
    try:
        query = db.query(PatientOffer).join(Patient).join(Offer)
        if q:
            query = query.filter(or_(Patient.full_name.ilike(f"%{q}%"), Patient.mobile.ilike(f"%{q}%")))
        if status:
            query = query.filter(PatientOffer.status == status)
        if campaign_id:
            query = query.filter(PatientOffer.campaign_id == campaign_id)
        try:
            if start:
                query = query.filter(PatientOffer.created_at >= date.fromisoformat(start))
            if end:
                query = query.filter(PatientOffer.created_at < date.fromisoformat(end) + timedelta(days=1))
        except ValueError:
            return request.app.state.templates.TemplateResponse(request, "patients.html", _context(
                request, rows=[], offers=[], campaigns=[], q=q, status=status, campaign_id=campaign_id, start=start, end=end,
                error="Dates must use YYYY-MM-DD.", list_url="/staff/patients", register_url="/staff/register", detail_prefix="/staff/patients",
            ), status_code=422)
        return request.app.state.templates.TemplateResponse(request, "patients.html", _context(
            request, rows=query.order_by(PatientOffer.created_at.desc()).all(),
            offers=db.query(Offer).order_by(Offer.name).all(), campaigns=db.query(Campaign).order_by(Campaign.name).all(),
            q=q, status=status, campaign_id=campaign_id, start=start, end=end,
            list_url="/staff/patients", register_url="/staff/register", detail_prefix="/staff/patients",
        ))
    finally:
        db.close()


@router.get("/staff/patients/{patient_id}")
def patient_detail(request: Request, patient_id: int):
    guard = require_staff(request)
    if guard:
        return guard
    db = request.app.state.db()
    try:
        patient = db.get(Patient, patient_id)
        if not patient:
            return RedirectResponse("/staff/patients", status_code=303)
        coupon = max(patient.offers, key=lambda item: item.created_at) if patient.offers else None
        events = db.query(AuditLog).filter(AuditLog.patient_id == patient.id).order_by(AuditLog.timestamp.desc()).all()
        return request.app.state.templates.TemplateResponse(request, "patient_detail.html", _context(
            request, patient=patient, coupon=coupon, events=events, back_url="/staff/patients",
            validate_url="/staff/validate", delivery_prefix=f"/staff/patients/{patient.id}/delivery", can_cancel=False,
        ))
    finally:
        db.close()


@router.post("/staff/patients/{patient_id}/delivery/{channel}")
def resend_delivery(request: Request, patient_id: int, channel: str, _csrf: None = Depends(require_csrf)):
    guard = require_staff(request)
    if guard:
        return guard
    channel = channel.upper()
    db = request.app.state.db()
    try:
        patient = db.get(Patient, patient_id)
        coupon = max(patient.offers, key=lambda item: item.created_at) if patient and patient.offers else None
        if channel not in {"EMAIL", "WHATSAPP"} or not coupon:
            return RedirectResponse(f"/staff/patients/{patient_id}?message=Delivery is unavailable", status_code=303)
        try:
            result = send_qr_delivery(db, patient, coupon, channel, request.session["user"])
        except ValueError as exc:
            return RedirectResponse(f"/staff/patients/{patient_id}?message={exc}", status_code=303)
        return RedirectResponse(f"/staff/patients/{patient_id}?message={channel.title()} delivery {result['status'].lower()}", status_code=303)
    finally:
        db.close()


@router.get("/staff/validate")
def validate_page(request: Request):
    guard = require_staff(request)
    if guard:
        return guard
    return request.app.state.templates.TemplateResponse(request, "validate.html", _context(
        request, result=None, token="", form_action="/staff/validate", back_url="/staff/home",
    ))


@router.post("/staff/validate")
def validate_submit(request: Request, token: str = Form(...), _csrf: None = Depends(require_csrf)):
    guard = require_staff(request)
    if guard:
        return guard
    db = request.app.state.db()
    try:
        coupon = find_coupon(db, token)
        if not coupon:
            result = {"kind": "INVALID", "message": "This QR/token is not registered in the Smriti Raj Dentistry system."}
            audit(db, request.session["user"], "QR_VALIDATED", details={"result": "INVALID"})
        else:
            if refresh_expiry(coupon, utc_now()):
                audit(db, request.session["user"], "QR_EXPIRED", coupon.id, coupon.patient_id)
            result = result_for(coupon)
            audit(db, request.session["user"], "QR_VALIDATED", coupon.id, coupon.patient_id, {"result": result["kind"]})
        db.commit()
        return request.app.state.templates.TemplateResponse(request, "validate.html", _context(
            request, result=result, token="", form_action="/staff/validate", back_url="/staff/home",
            redeem_url=f"/staff/patients/{coupon.patient_id}/redeem" if coupon else None,
        ))
    finally:
        db.close()


@router.get("/staff/validate/result/{coupon_uid}")
def validation_result(request: Request, coupon_uid: str):
    guard = require_staff(request)
    if guard:
        return guard
    db = request.app.state.db()
    try:
        coupon = db.execute(select(PatientOffer).where(PatientOffer.coupon_uid == coupon_uid)).scalar_one_or_none()
        if not coupon:
            return RedirectResponse("/staff/validate", status_code=303)
        refresh_expiry(coupon, utc_now())
        db.commit()
        return request.app.state.templates.TemplateResponse(request, "validate.html", _context(
            request, result=result_for(coupon), token="", form_action="/staff/validate", back_url="/staff/home",
            redeem_url=f"/staff/patients/{coupon.patient_id}/redeem",
        ))
    finally:
        db.close()


@router.post("/staff/patients/{patient_id}/redeem")
def redeem(request: Request, patient_id: int, _csrf: None = Depends(require_csrf)):
    guard = require_staff(request)
    if guard:
        return guard
    db = request.app.state.db()
    try:
        patient = db.get(Patient, patient_id)
        coupon = max(patient.offers, key=lambda item: item.created_at) if patient and patient.offers else None
        if not coupon:
            return RedirectResponse("/staff/validate", status_code=303)
        if redeem_atomic(db, coupon.id, request.session["user"], utc_now()):
            audit(db, request.session["user"], "QR_REDEEMED", coupon.id, patient.id)
            db.commit()
        return RedirectResponse(f"/staff/validate/result/{coupon.coupon_uid}", status_code=303)
    finally:
        db.close()
