from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, RedirectResponse
from ..auth import require_auth
from ..models import PatientOffer
from ..qr_service import ensure_qr

router = APIRouter()

@router.get("/offers")
def offers(request: Request):
    guard = require_auth(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        rows = db.query(PatientOffer).order_by(PatientOffer.created_at.desc()).all()
        return request.app.state.templates.TemplateResponse(request, "offers.html", {"request": request, "rows": rows})
    finally:
        db.close()

@router.get("/qr/{coupon_uid}.png")
def qr_image(request: Request, coupon_uid: str):
    guard = require_auth(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        coupon = db.query(PatientOffer).filter(PatientOffer.coupon_uid == coupon_uid).first()
    finally:
        db.close()
    if not coupon:
        return RedirectResponse("/offers", status_code=303)
    try:
        path = ensure_qr(coupon_uid, coupon.secure_token_hash)
    except FileNotFoundError:
        return RedirectResponse(f"/patients/{coupon.patient_id}?message=QR file unavailable", status_code=303)
    return FileResponse(path, media_type="image/png", filename=path.name)

@router.get("/qr/{coupon_uid}/download")
def qr_download(request: Request, coupon_uid: str):
    guard = require_auth(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        coupon = db.query(PatientOffer).filter(PatientOffer.coupon_uid == coupon_uid).first()
    finally:
        db.close()
    if not coupon:
        return RedirectResponse("/offers", status_code=303)
    try:
        path = ensure_qr(coupon_uid, coupon.secure_token_hash)
    except FileNotFoundError:
        return RedirectResponse(f"/patients/{coupon.patient_id}?message=QR file unavailable", status_code=303)
    return FileResponse(path, media_type="image/png", filename=f"{coupon_uid}.png", headers={"Content-Disposition": f'attachment; filename="{coupon_uid}.png"'})

@router.get("/qr/{coupon_uid}/print")
def qr_print(request: Request, coupon_uid: str):
    guard = require_auth(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        coupon = db.query(PatientOffer).filter(PatientOffer.coupon_uid == coupon_uid).first()
        if not coupon:
            return RedirectResponse("/offers", status_code=303)
        return request.app.state.templates.TemplateResponse(request, "print_coupon.html", {"request": request, "coupon": coupon})
    finally:
        db.close()
