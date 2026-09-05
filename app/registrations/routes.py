from fastapi import APIRouter, Request
from ..auth import require_admin
from ..models import PatientOffer

router = APIRouter()


@router.get("/offers")
def offers(request: Request):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        rows = db.query(PatientOffer).order_by(PatientOffer.created_at.desc()).all()
        return request.app.state.templates.TemplateResponse(request, "offers.html", {"request": request, "rows": rows})
    finally:
        db.close()


@router.get("/redemptions")
def redemptions(request: Request):
    guard = require_admin(request)
    if guard:
        return guard
    db = request.app.state.db()
    try:
        rows = db.query(PatientOffer).filter(PatientOffer.status == "REDEEMED").order_by(PatientOffer.redeemed_at.desc()).all()
        return request.app.state.templates.TemplateResponse(request, "redemptions.html", {"request": request, "rows": rows})
    finally:
        db.close()
