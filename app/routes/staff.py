from fastapi import APIRouter, Request
from ..auth import require_staff_or_admin
from ..models import Campaign, PatientOffer

router = APIRouter()

@router.get("/staff")
def staff_home(request: Request):
    guard = require_staff_or_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        campaigns = db.query(Campaign).filter(Campaign.status == "ACTIVE").order_by(Campaign.start_date.desc()).all()
        active_qrs = db.query(PatientOffer).filter(PatientOffer.status == "ACTIVE").count()
        return request.app.state.templates.TemplateResponse(request, "staff_home.html", {"request": request, "campaigns": campaigns, "active_qrs": active_qrs})
    finally: db.close()
