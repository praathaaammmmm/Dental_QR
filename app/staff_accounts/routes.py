from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from ..audit_service import audit
from ..auth import password_hasher, require_admin
from ..models import StaffUser
from ..query_params import optional_int
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
        restore_id = optional_int(request.query_params.get("restore_id"))
        restore_candidate = None
        if restore_id:
            candidate = db.get(StaffUser, restore_id)
            if candidate and candidate.removed_at is not None and candidate.role == "staff":
                restore_candidate = candidate
        return request.app.state.templates.TemplateResponse(request, "staff.html", {
            "request": request, "rows": rows, "restore_candidate": restore_candidate,
        })
    finally: db.close()


@router.post("/staff")
def create_staff(request: Request, username: str = Form(...), password: str = Form(...), _csrf: None = Depends(require_csrf)):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        clean_username = username.strip()
        existing = db.query(StaffUser).filter(StaffUser.username == clean_username).first()
        if existing and existing.removed_at is not None:
            return RedirectResponse(
                f"/admin/staff?message=That username belongs to a removed staff account. Restore it below instead of creating a new one.&restore_id={existing.id}",
                status_code=303,
            )
        if existing:
            return RedirectResponse("/admin/staff?message=That staff username is already in use", status_code=303)
        user = StaffUser(username=clean_username, password_hash=password_hasher.hash(password), role="staff", active=True)
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
            return RedirectResponse("/admin/staff?message=That staff account was already removed.", status_code=303)
        user.active = False
        user.removed_at = utc_now()
        audit(db, request.session.get("user", "admin"), "STAFF_ACCOUNT_REMOVED", details={"username": user.username})
        db.commit()
        return RedirectResponse("/admin/staff?message=Staff account removed and access revoked.", status_code=303)
    finally: db.close()


@router.post("/staff/{staff_id}/restore")
def restore_staff(request: Request, staff_id: int, password: str = Form(...), _csrf: None = Depends(require_csrf)):
    """Reactivate a previously-removed account under its original username, rather than
    letting an admin create a second row -- the username is still taken at the database
    level by the removed row (it's archived, not deleted), so a plain create would just
    fail. Restoring preserves the row's id and every AuditLog entry already recorded
    under its username; only active/removed_at/password_hash change, plus a new
    STAFF_ACCOUNT_RESTORED entry. Same defensive role check as remove_staff: the
    clinic/admin account is never a StaffUser row, so this can only ever affect staff.
    """
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        user = db.get(StaffUser, staff_id)
        if not user:
            return RedirectResponse("/admin/staff?message=Staff account not found", status_code=303)
        if user.role != "staff":
            return RedirectResponse("/admin/staff?message=This account cannot be restored", status_code=303)
        if user.removed_at is None:
            return RedirectResponse("/admin/staff?message=That staff account is not removed", status_code=303)
        user.active = True
        user.removed_at = None
        user.password_hash = password_hasher.hash(password)
        audit(db, request.session.get("user", "admin"), "STAFF_ACCOUNT_RESTORED", details={"username": user.username})
        db.commit()
        return RedirectResponse("/admin/staff?message=Staff account restored and access re-enabled.", status_code=303)
    finally: db.close()
