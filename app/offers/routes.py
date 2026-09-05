from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from ..audit_service import audit
from ..auth import require_admin
from ..models import Offer
from ..security import require_csrf

router = APIRouter(prefix="/admin")


@router.get("/services")
def service_list(request: Request):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        rows = db.query(Offer).order_by(Offer.name).all()
        return request.app.state.templates.TemplateResponse(request, "services.html", {"request": request, "rows": rows})
    finally: db.close()


@router.post("/services")
def create_service(request: Request, name: str = Form(...), description: str = Form(...), _csrf: None = Depends(require_csrf)):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        offer = Offer(name=" ".join(name.split()), description=description.strip(), active=True)
        db.add(offer)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return RedirectResponse("/admin/services?message=A service with that name already exists", status_code=303)
        audit(db, request.session.get("user", "admin"), "SERVICE_CREATED", details={"name": offer.name})
        db.commit()
        return RedirectResponse("/admin/services?message=Service created", status_code=303)
    finally: db.close()


@router.post("/services/{offer_id}/toggle")
def toggle_service(request: Request, offer_id: int, _csrf: None = Depends(require_csrf)):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        offer = db.get(Offer, offer_id)
        if not offer:
            return RedirectResponse("/admin/services?message=Service not found", status_code=303)
        offer.active = not offer.active
        audit(db, request.session.get("user", "admin"), "SERVICE_UPDATED", details={"name": offer.name, "active": offer.active})
        db.commit()
        return RedirectResponse("/admin/services?message=Service updated", status_code=303)
    finally: db.close()
