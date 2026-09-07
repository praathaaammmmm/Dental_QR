from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.sessions import SessionMiddleware
from .auth import is_authenticated
from .beneficiary_categories import CATEGORY_LABELS
from .database import Base, engine, SessionLocal
from .models import Offer
from .config import ALLOWED_HOSTS, APP_ENV, SESSION_MAX_AGE_SECONDS, SESSION_HTTPS_ONLY, SESSION_SECRET_KEY, validate_security_config
from .security import SecurityHeadersMiddleware, get_csrf_token
from .time_utils import format_clinic_time


def seed_default_offers() -> None:
    db = SessionLocal()
    try:
        defaults = [
            ("Free In-House Zirconia Crown", "Complimentary in-house zirconia crown campaign offer."),
            ("Free In-House Aligner Scan", "Complimentary in-house aligner scan campaign offer."),
        ]
        for name, description in defaults:
            if not db.query(Offer).filter(Offer.name == name).first():
                db.add(Offer(name=name, description=description))
        db.commit()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    validate_security_config()
    if APP_ENV != "production":
        Base.metadata.create_all(bind=engine)
    seed_default_offers()
    yield

app = FastAPI(title="Smriti Raj Dentistry - QR Offer Management System", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET_KEY,
    session_cookie="srd_clinic_session",
    max_age=SESSION_MAX_AGE_SECONDS,
    same_site="lax",
    https_only=SESSION_HTTPS_ONLY,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals["csrf_token"] = get_csrf_token
templates.env.filters["clinic_time"] = format_clinic_time
templates.env.filters["category_label"] = lambda value: CATEGORY_LABELS.get(value, value)
app.state.templates = templates
app.state.db = SessionLocal


@app.exception_handler(StarletteHTTPException)
async def friendly_http_exception_handler(request: Request, exc: StarletteHTTPException):
    """A 404 (e.g. a stale/bookmarked link, or a POST-only action reached by a plain GET
    navigation) or 405 (right path, wrong method -- typically the same POST-only-action
    case) must never show the raw `{"detail": ...}` JSON FastAPI returns by default on an
    admin/staff browser page. The n8n delivery webhook is a machine API, not a browser
    page, so it keeps its normal JSON error contract; every other status code everywhere
    also keeps FastAPI's normal JSON error handling, unchanged.
    """
    if exc.status_code not in (404, 405) or request.url.path.startswith("/webhooks/"):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=getattr(exc, "headers", None))
    role = request.session.get("role")
    home_url = "/staff/home" if role == "staff" else "/admin/dashboard" if role == "admin" else "/login"
    if exc.status_code == 404:
        heading, message = "Page not found", "The page you're looking for doesn't exist or may have moved."
    else:
        heading = "That action isn't available this way"
        message = "This action can only be triggered from its button or link, not by navigating to it directly."
    return templates.TemplateResponse(request, "error.html", {
        "request": request, "status_code": exc.status_code, "heading": heading,
        "message": message, "home_url": home_url,
    }, status_code=exc.status_code)

from .routes import auth, patients, validation, staff
from .audit import routes as audit_routes
from .campaigns import routes as campaigns_routes
from .notifications import routes as notifications_routes
from .offers import routes as offers_routes
from .qr import routes as qr_routes
from .registrations import routes as registrations_routes
from .reporting import routes as reporting_routes
from .staff_accounts import routes as staff_accounts_routes

app.include_router(auth.router)
app.include_router(patients.router)
app.include_router(validation.router)
app.include_router(staff.router)
app.include_router(audit_routes.router)
app.include_router(campaigns_routes.router)
app.include_router(notifications_routes.router)
app.include_router(offers_routes.router)
app.include_router(qr_routes.router)
app.include_router(registrations_routes.router)
app.include_router(reporting_routes.router)
app.include_router(staff_accounts_routes.router)

@app.get("/", include_in_schema=False)
def root(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=303)
    if request.session.get("role") == "staff":
        return RedirectResponse("/staff/home", status_code=303)
    return RedirectResponse("/admin/dashboard", status_code=303)


@app.get("/health", include_in_schema=False)
def health():
    return {"status": "ok"}


@app.get("/ready", include_in_schema=False)
def ready():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503)
