import secrets
from fastapi import Request
from fastapi.responses import RedirectResponse
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from .config import CLINIC_PASSWORD_HASH, CLINIC_USERNAME, SESSION_VERSION
from .database import SessionLocal
from .models import StaffUser

SESSION_USER = "admin"
password_hasher = PasswordHasher()

def verify_credentials(username: str, password: str) -> bool:
    username_ok = secrets.compare_digest(username.strip(), CLINIC_USERNAME)
    try:
        password_ok = password_hasher.verify(CLINIC_PASSWORD_HASH, password)
    except (InvalidHashError, VerificationError):
        password_ok = False
    return username_ok and password_ok

def authenticate_user(username: str, password: str):
    if verify_credentials(username, password):
        return {"username": SESSION_USER, "role": "admin"}
    db = SessionLocal()
    try:
        user = db.query(StaffUser).filter(StaffUser.username == username.strip(), StaffUser.active == True).first()
        if user:
            try:
                if password_hasher.verify(user.password_hash, password):
                    return {"username": user.username, "role": user.role}
            except (InvalidHashError, VerificationError):
                pass
        return None
    finally:
        db.close()

def is_authenticated(request: Request) -> bool:
    if not request.session.get("user") or request.session.get("session_version") != SESSION_VERSION:
        return False
    if request.session.get("role", "admin") == "admin":
        return True
    db = SessionLocal()
    try:
        return bool(db.query(StaffUser.id).filter(StaffUser.username == request.session.get("user"), StaffUser.active == True).first())
    finally:
        db.close()

def require_auth(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=303)
    return None

def require_admin(request: Request):
    guard = require_auth(request)
    if guard:
        return guard
    if request.session.get("role", "admin") != "admin":
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("Admin access required", status_code=403)
    return None

def require_staff_or_admin(request: Request):
    return require_auth(request)
