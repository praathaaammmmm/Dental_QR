from datetime import date
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from ..audit_service import audit
from ..auth import require_admin
from ..models import Campaign, Offer
from ..security import require_csrf
from ..reporting.service import counts

router = APIRouter(prefix="/admin")


@router.get("/campaigns")
def campaigns(request: Request):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        rows = db.query(Campaign).order_by(Campaign.created_at.desc()).all()
        performance = []
        for campaign in rows:
            issued, redeemed, expired = counts(db, campaign.id)
            performance.append({"campaign": campaign, "issued": issued, "redeemed": redeemed, "expired": expired, "conversion": round(redeemed * 100 / issued, 1) if issued else 0})
        return request.app.state.templates.TemplateResponse(request, "campaigns.html", {"request": request, "rows": rows, "performance": performance, "offers": db.query(Offer).filter(Offer.active == True).order_by(Offer.name).all()})
    finally: db.close()


@router.post("/campaigns")
def create_campaign(request: Request, name: str = Form(...), start_date: date = Form(...), end_date: date = Form(...), offer_ids: list[int] = Form([]), _csrf: None = Depends(require_csrf)):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        if end_date < start_date:
            return RedirectResponse("/admin/campaigns?message=End date must be on or after start date", status_code=303)
        campaign = Campaign(name=" ".join(name.split()), start_date=start_date, end_date=end_date, created_by=request.session.get("user", "admin"), status="DRAFT")
        campaign.offers = db.query(Offer).filter(Offer.id.in_(offer_ids)).all() if offer_ids else []
        db.add(campaign); db.flush(); audit(db, request.session.get("user", "admin"), "CAMPAIGN_CREATED", details={"campaign": campaign.name}); db.commit()
        return RedirectResponse(f"/admin/campaigns/{campaign.id}?message=Campaign created", status_code=303)
    finally: db.close()


def update_status(request, campaign_id, status):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        campaign = db.get(Campaign, campaign_id)
        if not campaign: return RedirectResponse("/admin/campaigns", status_code=303)
        campaign.status = status; audit(db, request.session.get("user", "admin"), f"CAMPAIGN_{status}", details={"campaign": campaign.name}); db.commit()
        return RedirectResponse(f"/admin/campaigns/{campaign_id}", status_code=303)
    finally: db.close()


@router.post("/campaigns/{campaign_id}/start")
def start(request: Request, campaign_id: int, _csrf: None = Depends(require_csrf)): return update_status(request, campaign_id, "ACTIVE")
@router.post("/campaigns/{campaign_id}/pause")
def pause(request: Request, campaign_id: int, _csrf: None = Depends(require_csrf)): return update_status(request, campaign_id, "PAUSED")
@router.post("/campaigns/{campaign_id}/close")
def close(request: Request, campaign_id: int, _csrf: None = Depends(require_csrf)): return update_status(request, campaign_id, "CLOSED")


@router.get("/campaigns/{campaign_id}")
def campaign_detail(request: Request, campaign_id: int):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        campaign = db.get(Campaign, campaign_id)
        if not campaign: return RedirectResponse("/admin/campaigns", status_code=303)
        issued, redeemed, expired = counts(db, campaign_id)
        service_stats = []
        for offer in campaign.offers:
            service_issued, service_redeemed, service_expired = counts(db, campaign_id, offer.id)
            service_stats.append({"name": offer.name, "issued": service_issued, "redeemed": service_redeemed, "expired": service_expired, "conversion": round(service_redeemed * 100 / service_issued, 1) if service_issued else 0})
        return request.app.state.templates.TemplateResponse(request, "campaign_detail.html", {"request": request, "campaign": campaign, "issued": issued, "redeemed": redeemed, "expired": expired, "conversion": round(redeemed * 100 / issued, 1) if issued else 0, "service_stats": service_stats})
    finally: db.close()
