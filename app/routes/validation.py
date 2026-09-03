import re
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from ..auth import require_auth
from ..models import PatientOffer
from ..coupon_service import refresh_expiry, redeem_atomic
from ..audit_service import audit
from ..security import require_csrf
from ..time_utils import utc_now
from ..qr_service import token_for, token_hash

router = APIRouter()

def find_coupon(db, token):
    value = token.strip()
    if re.fullmatch(r"SRD-[A-F0-9]{8}", value, re.IGNORECASE):
        coupon = db.execute(
            select(PatientOffer).where(PatientOffer.coupon_uid == value.upper())
        ).scalar_one_or_none()
        if coupon and coupon.secure_token_hash == token_hash(token_for(coupon.coupon_uid)):
            return coupon
        return None
    return db.execute(
        select(PatientOffer).where(PatientOffer.secure_token_hash == token_hash(value))
    ).scalar_one_or_none()

def result_for(coupon):
    if coupon.status == "REDEEMED": return {"kind": "REDEEMED", "coupon": coupon}
    if coupon.status == "CANCELLED": return {"kind": "CANCELLED", "coupon": coupon}
    if coupon.status == "EXPIRED": return {"kind": "EXPIRED", "coupon": coupon}
    return {"kind": "VALID", "coupon": coupon}

@router.get("/validate")
def validate_page(request: Request):
    guard = require_auth(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        return request.app.state.templates.TemplateResponse(request, "validate.html", {"request": request, "result": None, "token": ""})
    finally:
        db.close()

@router.post("/validate")
def validate_submit(request: Request, token: str = Form(...), _csrf: None = Depends(require_csrf)):
    guard = require_auth(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        coupon = find_coupon(db, token)
        if not coupon:
            result = {"kind": "INVALID", "message": "This QR/token is not registered in the Smriti Raj Dentistry system."}
        else:
            changed = refresh_expiry(coupon, utc_now())
            if changed:
                audit(db, request.session.get("user", "admin"), "QR_EXPIRED", coupon.id, coupon.patient_id)
            result = result_for(coupon)
            audit(db, request.session.get("user", "admin"), "QR_VALIDATED", coupon.id, coupon.patient_id, {"result": result["kind"]})
            db.commit()
        return request.app.state.templates.TemplateResponse(request, "validate.html", {"request": request, "result": result, "token": ""})
    finally:
        db.close()

@router.get("/validate/result/{coupon_uid}")
def validation_result(request: Request, coupon_uid: str):
    guard = require_auth(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        coupon = db.execute(select(PatientOffer).where(PatientOffer.coupon_uid == coupon_uid)).scalar_one_or_none()
        if not coupon:
            return RedirectResponse("/validate", status_code=303)
        refresh_expiry(coupon, utc_now())
        db.commit()
        return request.app.state.templates.TemplateResponse(request, "validate.html", {"request": request, "result": result_for(coupon), "token": ""})
    finally:
        db.close()

@router.post("/redeem/{coupon_id}")
def redeem(request: Request, coupon_id: int, _csrf: None = Depends(require_csrf)):
    guard = require_auth(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        coupon = db.get(PatientOffer, coupon_id)
        if not coupon:
            return RedirectResponse("/validate", status_code=303)
        now = utc_now()
        ok = redeem_atomic(db, coupon.id, request.session.get("user", "admin"), now)
        if ok:
            # Atomic update succeeded. Audit in a separate transaction.
            db.add(__import__("app.models", fromlist=["AuditLog"]).AuditLog(
                user=request.session.get("user", "admin"),
                action="QR_REDEEMED",
                coupon_id=coupon.id,
                patient_id=coupon.patient_id,
            ))
            db.commit()
            return RedirectResponse(f"/validate/result/{coupon.coupon_uid}", status_code=303)
        return RedirectResponse(f"/validate/result/{coupon.coupon_uid}", status_code=303)
    finally:
        db.close()
