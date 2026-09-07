from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from ..audit_service import audit
from ..auth import password_hasher, require_admin
from ..models import StaffUser
from ..security import require_csrf
from ..time_utils import utc_now

router = APIRouter(prefix="/admin")


@router.get("/staff")
def staff_list(request: Request):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        rows = db.query(StaffUser).filter(StaffUser.removed_at.is_(None)).order_by(StaffUser.username).all()
        return request.app.state.templates.TemplateResponse(request, "staff.html", {"request": request, "rows": rows})
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
        if not user or user.removed_at:
            return RedirectResponse("/admin/staff?message=Staff account not found", status_code=303)
        user.active = not user.active
        audit(db, request.session.get("user", "admin"), "STAFF_ACCOUNT_UPDATED", details={"username": user.username, "active": user.active})
        db.commit()
        return RedirectResponse("/admin/staff?message=Staff account updated", status_code=303)
    finally: db.close()


@router.post("/staff/{staff_id}/remove")
def remove_staff(request: Request, staff_id: int, _csrf: None = Depends(require_csrf)):
    """Safe removal: revokes access immediately (active=False) and marks the account
    removed so it drops out of the normal staff list, but the row itself — and every
    AuditLog entry recorded under this username — is preserved rather than deleted.

    The clinic/admin account is never a StaffUser row (it's env-var based, role never
    "admin" here), so this route can only ever affect a real "staff" row; the role check
    is still enforced defensively in case that invariant is ever broken elsewhere.
    """
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        user = db.get(StaffUser, staff_id)
        if not user:
            return RedirectResponse("/admin/staff?message=Staff account not found", status_code=303)
        if user.role != "staff":
            return RedirectResponse("/admin/staff?message=This account cannot be removed", status_code=303)
        if user.removed_at:
            return RedirectResponse("/admin/staff?message=Staff account already removed", status_code=303)
        user.active = False
        user.removed_at = utc_now()
        audit(db, request.session.get("user", "admin"), "STAFF_ACCOUNT_REMOVED", details={"username": user.username})
        db.commit()
        return RedirectResponse("/admin/staff?message=Staff account removed", status_code=303)
    finally: db.close()
