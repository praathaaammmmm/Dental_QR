from datetime import date
import csv
from io import StringIO
from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy import func
from ..auth import require_admin
from ..models import Campaign, Offer, PatientOffer, DeliveryLog
from ..security import require_csrf
from ..audit_service import audit
from ..models import StaffUser, AuditLog
from argon2 import PasswordHasher

router = APIRouter(prefix="/admin")
password_hasher = PasswordHasher()

@router.get("/audit")
def audit_log(request: Request):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        rows = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(250).all()
        return request.app.state.templates.TemplateResponse(request, "audit.html", {"request": request, "rows": rows})
    finally: db.close()

@router.get("/staff")
def staff_list(request: Request):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        return request.app.state.templates.TemplateResponse(request, "staff.html", {"request": request, "rows": db.query(StaffUser).order_by(StaffUser.username).all()})
    finally: db.close()

@router.post("/staff")
def create_staff(request: Request, username: str = Form(...), password: str = Form(...), _csrf: None = Depends(require_csrf)):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        user = StaffUser(username=username.strip(), password_hash=password_hasher.hash(password), role="staff", active=True)
        db.add(user); db.commit()
        return RedirectResponse("/admin/staff?message=Staff account created", status_code=303)
    finally: db.close()

@router.post("/staff/{staff_id}/toggle")
def toggle_staff(request: Request, staff_id: int, _csrf: None = Depends(require_csrf)):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        user = db.get(StaffUser, staff_id)
        if not user:
            return RedirectResponse("/admin/staff?message=Staff account not found", status_code=303)
        user.active = not user.active
        audit(db, request.session.get("user", "admin"), "STAFF_ACCOUNT_UPDATED", details={"username": user.username, "active": user.active})
        db.commit()
        return RedirectResponse("/admin/staff?message=Staff account updated", status_code=303)
    finally: db.close()

@router.get("/reports/campaigns.csv")
def campaign_report(request: Request):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Campaign", "Start date", "End date", "Status", "Issued", "Redeemed", "Expired", "Conversion rate"])
        campaigns = db.query(Campaign).order_by(Campaign.created_at.desc()).all()
        for campaign in campaigns:
            issued, redeemed, expired = counts(db, campaign.id)
            writer.writerow([campaign.name, campaign.start_date, campaign.end_date, campaign.status, issued, redeemed, expired, f"{(redeemed * 100 / issued) if issued else 0:.1f}%"])
        output.seek(0)
        return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=campaign-performance.csv"})
    finally:
        db.close()

def counts(db, campaign_id=None, offer_id=None, start=None, end=None):
    q = db.query(PatientOffer)
    if campaign_id: q = q.filter(PatientOffer.campaign_id == campaign_id)
    if offer_id: q = q.filter(PatientOffer.offer_id == offer_id)
    if start: q = q.filter(PatientOffer.created_at >= start)
    if end: q = q.filter(PatientOffer.created_at <= end)
    issued = q.count()
    redeemed = q.filter(PatientOffer.status == "REDEEMED").count()
    expired = q.filter(PatientOffer.status == "EXPIRED").count()
    return issued, redeemed, expired

@router.get("/dashboard")
def dashboard(request: Request, campaign_id: int | None = None, offer_id: int | None = None, start: str = Query(""), end: str = Query("")):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        start_date = date.fromisoformat(start) if start else None
        end_date = date.fromisoformat(end) if end else None
        issued, redeemed, expired = counts(db, campaign_id, offer_id, start_date, end_date)
        conversion = round(redeemed * 100 / issued, 1) if issued else 0
        campaigns = db.query(Campaign).order_by(Campaign.created_at.desc()).all()
        offers = db.query(Offer).order_by(Offer.name).all()
        deliveries = db.query(DeliveryLog).join(PatientOffer, DeliveryLog.coupon_id == PatientOffer.id)
        if campaign_id: deliveries = deliveries.filter(PatientOffer.campaign_id == campaign_id)
        if offer_id: deliveries = deliveries.filter(PatientOffer.offer_id == offer_id)
        if start_date: deliveries = deliveries.filter(DeliveryLog.sent_at >= start_date)
        if end_date: deliveries = deliveries.filter(DeliveryLog.sent_at < end_date.fromordinal(end_date.toordinal() + 1))
        email_total = deliveries.filter(DeliveryLog.channel == "EMAIL").count()
        whatsapp_total = deliveries.filter(DeliveryLog.channel == "WHATSAPP").count()
        email_sent = deliveries.filter(DeliveryLog.channel == "EMAIL", DeliveryLog.status.in_(["SENT", "DELIVERED"])).count()
        whatsapp_sent = deliveries.filter(DeliveryLog.channel == "WHATSAPP", DeliveryLog.status.in_(["SENT", "DELIVERED"])).count()
        return request.app.state.templates.TemplateResponse(request, "admin_dashboard.html", {"request": request, "issued": issued, "redeemed": redeemed, "expired": expired, "conversion": conversion, "campaigns": campaigns, "offers": offers, "campaign_id": campaign_id, "offer_id": offer_id, "start": start, "end": end, "email_rate": round(email_sent * 100 / email_total, 1) if email_total else 0, "whatsapp_rate": round(whatsapp_sent * 100 / whatsapp_total, 1) if whatsapp_total else 0})
    finally: db.close()

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
        return request.app.state.templates.TemplateResponse(request, "campaigns.html", {"request": request, "rows": rows, "performance": performance, "offers": db.query(Offer).order_by(Offer.name).all()})
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
