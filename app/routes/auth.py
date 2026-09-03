from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from threading import Lock
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from ..config import SESSION_VERSION
from ..auth import authenticate_staff, authenticate_user
from ..security import require_csrf

router = APIRouter()
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW = timedelta(minutes=15)
_attempts = defaultdict(deque)
_attempts_lock = Lock()

def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"

def _is_rate_limited(key: str) -> bool:
    now = datetime.now(timezone.utc)
    with _attempts_lock:
        attempts = _attempts[key]
        while attempts and now - attempts[0] > LOGIN_WINDOW:
            attempts.popleft()
        return len(attempts) >= MAX_LOGIN_ATTEMPTS

def _record_failure(key: str) -> None:
    with _attempts_lock:
        _attempts[key].append(datetime.now(timezone.utc))

def _clear_failures(key: str) -> None:
    with _attempts_lock:
        _attempts.pop(key, None)

@router.get("/login")
def login_page(request: Request):
    if request.session.get("user"):
        return RedirectResponse("/", status_code=303)
    return request.app.state.templates.TemplateResponse(
        request,
        "login.html", {"request": request, "error": None}
    )

@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), _csrf: None = Depends(require_csrf)):
    client_key = _client_key(request)
    if _is_rate_limited(client_key):
        return request.app.state.templates.TemplateResponse(
            request,
            "login.html",
            {"request": request, "error": "Too many login attempts. Try again later."},
            status_code=429,
        )
    identity = authenticate_user(username, password)
    if identity:
        _clear_failures(client_key)
        request.session.clear()
        request.session["user"] = identity["username"]
        request.session["role"] = identity["role"]
        request.session["session_version"] = SESSION_VERSION
        return RedirectResponse("/", status_code=303)
    _record_failure(client_key)
    return request.app.state.templates.TemplateResponse(
        request,
        "login.html", {"request": request, "error": "Invalid password"}
    )

@router.post("/logout")
def logout(request: Request, _csrf: None = Depends(require_csrf)):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/staff/login")
def staff_login_page(request: Request):
    if request.session.get("role") == "staff":
        return RedirectResponse("/staff/home", status_code=303)
    return request.app.state.templates.TemplateResponse(request, "login.html", {
        "request": request, "error": None, "login_action": "/staff/login",
        "login_title": "Staff workspace login",
        "login_lead": "Sign in to register patients and manage QR redemptions.",
    })


@router.post("/staff/login")
def staff_login(request: Request, username: str = Form(...), password: str = Form(...), _csrf: None = Depends(require_csrf)):
    client_key = _client_key(request)
    context = {
        "request": request, "login_action": "/staff/login",
        "login_title": "Staff workspace login",
        "login_lead": "Sign in to register patients and manage QR redemptions.",
    }
    if _is_rate_limited(client_key):
        return request.app.state.templates.TemplateResponse(request, "login.html", {
            **context, "error": "Too many login attempts. Try again later."
        }, status_code=429)
    identity = authenticate_staff(username, password)
    if identity:
        _clear_failures(client_key)
        request.session.clear()
        request.session["user"] = identity["username"]
        request.session["role"] = "staff"
        request.session["staff_user_id"] = identity["staff_user_id"]
        request.session["session_version"] = SESSION_VERSION
        return RedirectResponse("/staff/home", status_code=303)
    _record_failure(client_key)
    return request.app.state.templates.TemplateResponse(request, "login.html", {
        **context, "error": "Invalid staff username or password"
    })


@router.post("/staff/logout")
def staff_logout(request: Request, _csrf: None = Depends(require_csrf)):
    request.session.clear()
    return RedirectResponse("/staff/login", status_code=303)
