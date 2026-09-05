from fastapi import APIRouter, Request
from ..auth import require_admin
from ..models import AuditLog

router = APIRouter(prefix="/admin")


@router.get("/audit")
def audit_log(request: Request):
    guard = require_admin(request)
    if guard: return guard
    db = request.app.state.db()
    try:
        rows = db.query(AuditLog).order_by(AuditLog.timestamp.desc()).limit(250).all()
        return request.app.state.templates.TemplateResponse(request, "audit.html", {"request": request, "rows": rows})
    finally: db.close()
