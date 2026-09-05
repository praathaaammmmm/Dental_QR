from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from ..audit_service import audit
from ..auth import password_hasher, require_admin
from ..models import StaffUser
from ..security import require_csrf

router = APIRouter(prefix="/admin")


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
        db.add(user)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return RedirectResponse("/admin/staff?message=That staff username is already in use", status_code=303)
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
