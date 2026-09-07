import re
from datetime import date, timedelta

import pytest

from app.database import SessionLocal
from app.models import Campaign, Offer, PatientOffer
from app.registrations.service import OfferUnavailableError, register_patient_offer


def _make_campaign(db, name, offers):
    campaign = Campaign(
        name=name,
        start_date=date.today() - timedelta(days=1),
        end_date=date.today() + timedelta(days=1),
        status="ACTIVE",
        created_by="test",
    )
    campaign.offers = offers
    db.add(campaign)
    db.flush()
    return campaign


def _register(db, *, campaign_id, offer_id, mobile):
    return register_patient_offer(
        db,
        full_name="Scoping Test Patient",
        mobile=mobile,
        email="",
        age="",
        gender="",
        city="",
        doctor_name="",
        campaign_name="",
        campaign_id=campaign_id,
        offer_id=offer_id,
        beneficiary_category="CGHS",
        consent_given=True,
        actor="admin",
    )


def _data_campaigns_for(html, offer_name):
    # Split into one chunk per rendered offer option so a lazy regex can't span
    # across labels and pick up a different offer's data-campaigns attribute.
    blocks = html.split('<label class="offer-option"')
    for block in blocks:
        if f"<b>{offer_name}</b>" not in block:
            continue
        match = re.search(r'data-campaigns="([^"]*)"', block)
        assert match, f"offer option for {offer_name!r} has no data-campaigns attribute"
        return set(filter(None, match.group(1).split(",")))
    raise AssertionError(f"could not find a rendered offer option for {offer_name!r}")


def test_each_campaign_exposes_only_its_own_services(client):
    db = SessionLocal()
    try:
        dalle_offer = Offer(name="Lakshay Anal Service", description="test", active=True)
        db.add(dalle_offer)
        db.flush()
        dalle = _make_campaign(db, "dalle", [dalle_offer])
        db.commit()
        dalle_id = dalle.id
    finally:
        db.close()

    page = client.get("/patients/register")
    assert page.status_code == 200
    html = page.text

    dalle_service_campaigns = _data_campaigns_for(html, "Lakshay Anal Service")
    zirconia_campaigns = _data_campaigns_for(html, "Free In-House Zirconia Crown")
    aligner_campaigns = _data_campaigns_for(html, "Free In-House Aligner Scan")

    assert str(dalle_id) in dalle_service_campaigns
    assert str(dalle_id) not in zirconia_campaigns
    assert str(dalle_id) not in aligner_campaigns


def test_cross_campaign_service_submission_rejected(client):
    db = SessionLocal()
    try:
        dalle_offer = Offer(name="Lakshay Anal Service 2", description="test", active=True)
        db.add(dalle_offer)
        db.flush()
        dalle = _make_campaign(db, "dalle-2", [dalle_offer])
        db.commit()
        dalle_id = dalle.id
    finally:
        db.close()

    # Direct service-layer call: campaign "dalle-2" only offers its own service, not
    # the fixture's "Free In-House Zirconia Crown" (offer_id=1).
    db = SessionLocal()
    try:
        with pytest.raises(OfferUnavailableError):
            _register(db, campaign_id=dalle_id, offer_id=1, mobile="9999999975")
    finally:
        db.close()

    # A crafted HTTP request selecting the same mismatched pair must also be rejected.
    response = client.post("/patients/register", data={
        "full_name": "Crafted Request Patient",
        "mobile": "9999999974",
        "campaign_id": str(dalle_id),
        "offer_id": "1",
        "beneficiary_category": "CGHS",
        "consent_given": "true",
    })
    assert response.status_code == 422
    assert "not part of this campaign" in response.text
    assert db_count_patient_offers() == 0


def db_count_patient_offers():
    db = SessionLocal()
    try:
        return db.query(PatientOffer).count()
    finally:
        db.close()


def test_registration_rejected_when_campaign_has_no_offers_configured(client):
    db = SessionLocal()
    try:
        empty_campaign = _make_campaign(db, "no-offers-campaign", [])
        db.commit()
        empty_campaign_id = empty_campaign.id
    finally:
        db.close()

    db = SessionLocal()
    try:
        with pytest.raises(OfferUnavailableError):
            _register(db, campaign_id=empty_campaign_id, offer_id=1, mobile="9999999973")
    finally:
        db.close()


def test_normal_valid_registration_still_works(client):
    db = SessionLocal()
    try:
        dalle_offer = Offer(name="Lakshay Anal Service 3", description="test", active=True)
        db.add(dalle_offer)
        db.flush()
        dalle = _make_campaign(db, "dalle-3", [dalle_offer])
        db.commit()
        dalle_id, dalle_offer_id = dalle.id, dalle_offer.id
    finally:
        db.close()

    db = SessionLocal()
    try:
        coupon = _register(db, campaign_id=dalle_id, offer_id=dalle_offer_id, mobile="9999999972")
        assert coupon.id is not None
        assert coupon.campaign_id == dalle_id
        assert coupon.offer_id == dalle_offer_id
        assert db.query(PatientOffer).filter(PatientOffer.id == coupon.id).count() == 1
    finally:
        db.close()
