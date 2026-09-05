from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from ..auth import require_admin
from ..models import PatientOffer
from ..qr.service import find_coupon, refresh_expiry, redeem_atomic, result_for
from ..audit_service import audit
from ..security import require_csrf
from ..time_utils import utc_now

router = APIRouter()

@router.get("/validate")
def validate_page(request: Request):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        return request.app.state.templates.TemplateResponse(request, "validate.html", {"request": request, "result": None, "token": ""})
    finally:
        db.close()

@router.post("/validate")
def validate_submit(request: Request, token: str = Form(...), _csrf: None = Depends(require_csrf)):
    guard = require_admin(request)
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
    guard = require_admin(request)
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
    guard = require_admin(request)
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
