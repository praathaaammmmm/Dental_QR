"""Aggregate, admin-only reporting queries for the CRM dashboard."""
from datetime import date

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from ..beneficiary_categories import ALL_CATEGORIES
from ..models import AuditLog, Campaign, DeliveryLog, Offer, Patient, PatientOffer, StaffUser
from ..time_utils import clinic_date_range_to_utc

# start/end are Asia/Kolkata calendar dates (as entered on the admin dashboard filter form).
# Every query below converts them to UTC bounds via clinic_date_range_to_utc before comparing
# against a stored (naive UTC) timestamp column, so this stays consistent with the staff
# patient list's date filter. end is inclusive of its entire local calendar day.


def _offer_conditions(campaign_id=None, offer_id=None, start: date | None = None, end: date | None = None, date_column=None):
    conditions = []
    if campaign_id:
        conditions.append(PatientOffer.campaign_id == campaign_id)
    if offer_id:
        conditions.append(PatientOffer.offer_id == offer_id)
    start_utc, end_utc = clinic_date_range_to_utc(start, end)
    if start_utc:
        conditions.append(date_column >= start_utc)
    if end_utc:
        conditions.append(date_column < end_utc)
    return conditions


def dashboard_summary(db: Session, campaign_id=None, offer_id=None, start: date | None = None, end: date | None = None) -> dict:
    conditions = _offer_conditions(campaign_id, offer_id, start, end, PatientOffer.created_at)
    row = db.execute(select(
        func.count(PatientOffer.id).label("issued"),
        func.coalesce(func.sum(case((PatientOffer.status == "REDEEMED", 1), else_=0)), 0).label("redeemed"),
        func.coalesce(func.sum(case((PatientOffer.status == "EXPIRED", 1), else_=0)), 0).label("expired"),
    ).where(*conditions)).mappings().one()
    return dict(row)


def delivery_summary(db: Session, campaign_id=None, offer_id=None, start: date | None = None, end: date | None = None) -> dict:
    conditions = _offer_conditions(campaign_id, offer_id, None, None, PatientOffer.created_at)
    start_utc, end_utc = clinic_date_range_to_utc(start, end)
    if start_utc:
        conditions.append(DeliveryLog.sent_at >= start_utc)
    if end_utc:
        conditions.append(DeliveryLog.sent_at < end_utc)
    row = db.execute(select(
        func.coalesce(func.sum(case((DeliveryLog.channel == "EMAIL", 1), else_=0)), 0).label("email_total"),
        func.coalesce(func.sum(case((and_(DeliveryLog.channel == "EMAIL", DeliveryLog.status.in_(["SENT", "DELIVERED"])), 1), else_=0)), 0).label("email_sent"),
        func.coalesce(func.sum(case((DeliveryLog.channel == "WHATSAPP", 1), else_=0)), 0).label("whatsapp_total"),
        func.coalesce(func.sum(case((and_(DeliveryLog.channel == "WHATSAPP", DeliveryLog.status.in_(["SENT", "DELIVERED"])), 1), else_=0)), 0).label("whatsapp_sent"),
    ).select_from(DeliveryLog).join(PatientOffer).where(*conditions)).mappings().one()
    return dict(row)


def daily_time_series(db: Session, campaign_id=None, offer_id=None, start: date | None = None, end: date | None = None) -> dict:
    registration_conditions = _offer_conditions(campaign_id, offer_id, start, end, PatientOffer.created_at)
    redemption_conditions = _offer_conditions(campaign_id, offer_id, start, end, PatientOffer.redeemed_at)
    redemption_conditions.extend([PatientOffer.status == "REDEEMED", PatientOffer.redeemed_at.is_not(None)])
    registrations = db.execute(select(
        func.date(PatientOffer.created_at).label("day"), func.count(PatientOffer.id).label("count"),
    ).where(*registration_conditions).group_by(func.date(PatientOffer.created_at)).order_by(func.date(PatientOffer.created_at))).mappings().all()
    redemptions = db.execute(select(
        func.date(PatientOffer.redeemed_at).label("day"), func.count(PatientOffer.id).label("count"),
    ).where(*redemption_conditions).group_by(func.date(PatientOffer.redeemed_at)).order_by(func.date(PatientOffer.redeemed_at))).mappings().all()
    return {"registrations": [dict(row) for row in registrations], "redemptions": [dict(row) for row in redemptions]}


def staff_performance(db: Session, start: date | None = None, end: date | None = None) -> list[dict]:
    join_conditions = [
        AuditLog.user == StaffUser.username,
        AuditLog.action.in_(["PATIENT_REGISTERED", "QR_REDEEMED"]),
    ]
    start_utc, end_utc = clinic_date_range_to_utc(start, end)
    if start_utc:
        join_conditions.append(AuditLog.timestamp >= start_utc)
    if end_utc:
        join_conditions.append(AuditLog.timestamp < end_utc)
    rows = db.execute(select(
        StaffUser.id.label("staff_id"), StaffUser.username.label("username"),
        func.coalesce(func.sum(case((AuditLog.action == "PATIENT_REGISTERED", 1), else_=0)), 0).label("registrations"),
        func.coalesce(func.sum(case((AuditLog.action == "QR_REDEEMED", 1), else_=0)), 0).label("redemptions"),
    ).select_from(StaffUser).outerjoin(AuditLog, and_(*join_conditions)).where(
        StaffUser.role == "staff"
    ).group_by(StaffUser.id, StaffUser.username).order_by(StaffUser.username)).mappings().all()
    return [dict(row) for row in rows]


def registrations_by_category(db: Session, campaign_id=None, offer_id=None, start: date | None = None, end: date | None = None) -> list[dict]:
    conditions = _offer_conditions(campaign_id, offer_id, start, end, PatientOffer.created_at)
    rows = db.execute(select(
        PatientOffer.beneficiary_category.label("category"), func.count(PatientOffer.id).label("count"),
    ).where(*conditions).group_by(PatientOffer.beneficiary_category)).mappings().all()
    counts = {row["category"]: row["count"] for row in rows}
    return [{"value": value, "label": label, "count": counts.get(value, 0)} for value, label in ALL_CATEGORIES]


def campaign_performance(db: Session, campaign_id=None, offer_id=None, start: date | None = None, end: date | None = None) -> list[dict]:
    coupon_join = [PatientOffer.campaign_id == Campaign.id]
    coupon_join.extend(_offer_conditions(campaign_id, offer_id, start, end, PatientOffer.created_at))
    rows = db.execute(select(
        Campaign.id, Campaign.name, Campaign.start_date, Campaign.end_date, Campaign.status,
        func.count(PatientOffer.id).label("issued"),
        func.coalesce(func.sum(case((PatientOffer.status == "REDEEMED", 1), else_=0)), 0).label("redeemed"),
        func.coalesce(func.sum(case((PatientOffer.status == "EXPIRED", 1), else_=0)), 0).label("expired"),
    ).select_from(Campaign).outerjoin(PatientOffer, and_(*coupon_join)).where(
        Campaign.id == campaign_id if campaign_id else True
    ).group_by(Campaign.id).order_by(Campaign.created_at.desc())).mappings().all()
    return [dict(row) for row in rows]


def counts(db: Session, campaign_id=None, offer_id=None, start: date | None = None, end: date | None = None) -> tuple[int, int, int]:
    """Thin (issued, redeemed, expired) convenience wrapper over ``dashboard_summary``,
    reused by the campaigns UI (campaign/service performance stats) as well as the
    dashboard itself — a read-only reporting query, not a reporting-domain mutation, so
    campaigns depending on it does not create a write-direction coupling back into
    reporting.
    """
    summary = dashboard_summary(db, campaign_id, offer_id, start, end)
    return summary["issued"], summary["redeemed"], summary["expired"]


def patient_export_rows(db: Session, campaign_id=None, offer_id=None, start: date | None = None, end: date | None = None):
    conditions = _offer_conditions(campaign_id, offer_id, start, end, PatientOffer.created_at)
    return db.execute(select(
        Patient.patient_uid, Patient.full_name, Patient.mobile, Patient.email, Patient.age, Patient.gender,
        Campaign.name.label("campaign"), Offer.name.label("service"), PatientOffer.coupon_uid,
        PatientOffer.created_at, PatientOffer.expires_at, PatientOffer.status, PatientOffer.redeemed_at,
        PatientOffer.redeemed_by, PatientOffer.beneficiary_category,
    ).select_from(PatientOffer).join(Patient).join(Offer).outerjoin(Campaign).where(*conditions).order_by(
        PatientOffer.created_at.desc()
    )).mappings().all()
