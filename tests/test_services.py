from app.database import SessionLocal
from app.models import Offer
from tests.test_staff_interface import _login_as_staff


def test_admin_can_create_service_and_it_lists_in_catalog(client):
    response = client.post(
        "/admin/services",
        data={"name": "Free Dental Cleaning", "description": "Complimentary cleaning session"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin/services?message=Service%20created"
    db = SessionLocal()
    try:
        offer = db.query(Offer).filter_by(name="Free Dental Cleaning").one()
        assert offer.active is True
        assert offer.description == "Complimentary cleaning session"
    finally:
        db.close()
    catalog = client.get("/admin/services")
    assert "Free Dental Cleaning" in catalog.text


def test_new_service_appears_in_staff_registration_service_selection(client):
    client.post("/admin/services", data={"name": "Free Root Canal Consult", "description": "Initial consult"})
    _login_as_staff(client)
    register_page = client.get("/staff/register")
    assert "Free Root Canal Consult" in register_page.text


def test_duplicate_service_name_is_rejected(client):
    response = client.post(
        "/admin/services",
        data={"name": "Free In-House Zirconia Crown", "description": "duplicate"},
        follow_redirects=True,
    )
    assert "already exists" in response.text
    db = SessionLocal()
    try:
        assert db.query(Offer).filter_by(name="Free In-House Zirconia Crown").count() == 1
    finally:
        db.close()


def test_deactivated_service_is_hidden_from_registration_but_keeps_history(client):
    db = SessionLocal()
    try:
        offer = db.query(Offer).filter_by(name="Free In-House Aligner Scan").one()
        offer_id = offer.id
    finally:
        db.close()

    response = client.post(f"/admin/services/{offer_id}/toggle", follow_redirects=False)
    assert response.status_code == 303

    db = SessionLocal()
    try:
        assert db.get(Offer, offer_id).active is False
    finally:
        db.close()

    admin_register_page = client.get("/patients/register")
    assert "Free In-House Aligner Scan" not in admin_register_page.text

    _login_as_staff(client)
    staff_register_page = client.get("/staff/register")
    assert "Free In-House Aligner Scan" not in staff_register_page.text
