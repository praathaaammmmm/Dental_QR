from fastapi import APIRouter, Request
from sqlalchemy import func
from ..auth import require_admin
from ..models import Patient, PatientOffer, Offer, DeliveryLog

router = APIRouter()

@router.get("/")
def dashboard(request: Request):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        total = db.query(func.count(Patient.id)).scalar() or 0
        active = db.query(func.count(PatientOffer.id)).filter(PatientOffer.status == "ACTIVE").scalar() or 0
        redeemed = db.query(func.count(PatientOffer.id)).filter(PatientOffer.status == "REDEEMED").scalar() or 0
        expired = db.query(func.count(PatientOffer.id)).filter(PatientOffer.status == "EXPIRED").scalar() or 0
        delivery_total = db.query(func.count(DeliveryLog.id)).scalar() or 0
        delivery_ok = db.query(func.count(DeliveryLog.id)).filter(DeliveryLog.status.in_(["SENT", "DELIVERED", "PREPARED"])).scalar() or 0
        delivery_percent = round(delivery_ok * 100 / delivery_total) if delivery_total else None
        recent = db.query(PatientOffer).order_by(PatientOffer.created_at.desc()).limit(8).all()
        offers = db.query(Offer).all()
        stats = []
        for offer in offers:
            stats.append({
                "name": offer.name,
                "total": db.query(func.count(PatientOffer.id)).filter(PatientOffer.offer_id == offer.id).scalar() or 0,
                "active": db.query(func.count(PatientOffer.id)).filter(PatientOffer.offer_id == offer.id, PatientOffer.status == "ACTIVE").scalar() or 0,
                "redeemed": db.query(func.count(PatientOffer.id)).filter(PatientOffer.offer_id == offer.id, PatientOffer.status == "REDEEMED").scalar() or 0,
            })
        return request.app.state.templates.TemplateResponse(request, "dashboard.html", {
            "request": request, "total": total, "active": active,
            "redeemed": redeemed, "expired": expired, "recent": recent, "stats": stats,
            "delivery_percent": delivery_percent,
        })
    finally:
        db.close()
