from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.sessions import SessionMiddleware
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
app.state.templates = templates
app.state.db = SessionLocal

from .routes import auth, dashboard, patients, coupons, validation, operations, admin, staff
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(patients.router)
app.include_router(coupons.router)
app.include_router(validation.router)
app.include_router(operations.router)
app.include_router(admin.router)
app.include_router(staff.router)

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
