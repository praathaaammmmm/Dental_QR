from datetime import date
import csv
from io import StringIO
from urllib.parse import urlencode
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse
from ..auth import require_admin
from ..models import Campaign, Offer
from ..query_params import optional_int
from .service import (
    campaign_performance, counts, daily_time_series, dashboard_summary, delivery_summary,
    patient_export_rows, registrations_by_category, staff_performance,
)

router = APIRouter(prefix="/admin")


@router.get("/reports/campaigns.csv")
def campaign_report(request: Request, campaign_id: str = Query(""), offer_id: str = Query(""), start: str = Query(""), end: str = Query("")):
    guard = require_admin(request)
    if guard: return guard
    campaign_id, offer_id = optional_int(campaign_id), optional_int(offer_id)
    db = request.app.state.db()
    try:
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Campaign", "Start date", "End date", "Status", "Issued", "Redeemed", "Expired", "Conversion rate"])
        start_date = date.fromisoformat(start) if start else None
        end_date = date.fromisoformat(end) if end else None
        for campaign in campaign_performance(db, campaign_id, offer_id, start_date, end_date):
            issued, redeemed = campaign["issued"], campaign["redeemed"]
            writer.writerow([campaign["name"], campaign["start_date"], campaign["end_date"], campaign["status"], issued, redeemed, campaign["expired"], f"{(redeemed * 100 / issued) if issued else 0:.1f}%"])
        output.seek(0)
        return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=campaign-performance.csv"})
    finally:
        db.close()


@router.get("/dashboard")
def dashboard(request: Request, campaign_id: str = Query(""), offer_id: str = Query(""), start: str = Query(""), end: str = Query("")):
    guard = require_admin(request)
    if guard: return guard
    campaign_id, offer_id = optional_int(campaign_id), optional_int(offer_id)
    db = request.app.state.db()
    try:
        start_date = date.fromisoformat(start) if start else None
        end_date = date.fromisoformat(end) if end else None
        summary = dashboard_summary(db, campaign_id, offer_id, start_date, end_date)
        issued, redeemed, expired = summary["issued"], summary["redeemed"], summary["expired"]
        conversion = round(redeemed * 100 / issued, 1) if issued else 0
        campaigns = db.query(Campaign).order_by(Campaign.created_at.desc()).all()
        offers = db.query(Offer).order_by(Offer.name).all()
        deliveries = delivery_summary(db, campaign_id, offer_id, start_date, end_date)
        report_query = urlencode({key: value for key, value in {
            "campaign_id": campaign_id, "offer_id": offer_id, "start": start, "end": end,
        }.items() if value not in (None, "")})
        return request.app.state.templates.TemplateResponse(request, "admin_dashboard.html", {
            "request": request, "issued": issued, "redeemed": redeemed, "expired": expired,
            "conversion": conversion, "campaigns": campaigns, "offers": offers,
            "campaign_id": campaign_id, "offer_id": offer_id, "start": start, "end": end,
            "email_rate": round(deliveries["email_sent"] * 100 / deliveries["email_total"], 1) if deliveries["email_total"] else 0,
            "whatsapp_rate": round(deliveries["whatsapp_sent"] * 100 / deliveries["whatsapp_total"], 1) if deliveries["whatsapp_total"] else 0,
            "time_series": daily_time_series(db, campaign_id, offer_id, start_date, end_date),
            "staff_performance": staff_performance(db, start_date, end_date),
            "category_breakdown": registrations_by_category(db, campaign_id, offer_id, start_date, end_date),
            "report_query": report_query,
        })
    finally: db.close()


@router.get("/reports/patients.csv")
def patient_report(request: Request, campaign_id: str = Query(""), offer_id: str = Query(""), start: str = Query(""), end: str = Query("")):
    guard = require_admin(request)
    if guard:
        return guard
    campaign_id, offer_id = optional_int(campaign_id), optional_int(offer_id)
    db = request.app.state.db()
    try:
        start_date = date.fromisoformat(start) if start else None
        end_date = date.fromisoformat(end) if end else None
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Patient ID", "Patient", "Mobile", "Email", "Age", "Gender", "Campaign", "Service", "Beneficiary Category", "Registration ID", "Registered", "Expires", "Status", "Redeemed", "Redeemed by"])
        for row in patient_export_rows(db, campaign_id, offer_id, start_date, end_date):
            writer.writerow([row["patient_uid"], row["full_name"], row["mobile"], row["email"], row["age"], row["gender"], row["campaign"], row["service"], row["beneficiary_category"], row["coupon_uid"], row["created_at"], row["expires_at"], row["status"], row["redeemed_at"], row["redeemed_by"]])
        output.seek(0)
        return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=patient-registrations.csv"})
    finally:
        db.close()
