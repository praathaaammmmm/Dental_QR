from datetime import timedelta
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import RedirectResponse
from ..config import SESSION_VERSION
from ..auth import authenticate_staff, authenticate_user
from ..security import (
    _attempts, clear_rate_limit_events, client_key, is_rate_limited,
    record_rate_limit_event, require_csrf,
)

router = APIRouter()
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW = timedelta(minutes=15)
def _is_rate_limited(key: str) -> bool:
    return is_rate_limited("login", key, MAX_LOGIN_ATTEMPTS, LOGIN_WINDOW)

def _record_failure(key: str) -> None:
    record_rate_limit_event("login", key)

def _clear_failures(key: str) -> None:
    clear_rate_limit_events("login", key)

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
    request_key = client_key(request)
    if _is_rate_limited(request_key):
        return request.app.state.templates.TemplateResponse(
            request,
            "login.html",
            {"request": request, "error": "Too many login attempts. Try again later."},
            status_code=429,
        )
    identity = authenticate_user(username, password)
    if identity:
        _clear_failures(request_key)
        request.session.clear()
        request.session["user"] = identity["username"]
        request.session["role"] = identity["role"]
        request.session["session_version"] = SESSION_VERSION
        return RedirectResponse("/", status_code=303)
    _record_failure(request_key)
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
        "login_title": "Staff Login",
        "login_lead": "Sign in to register patients and manage QR redemptions.",
        "username_label": "Staff username",
        "username_placeholder": "Enter staff username",
        "login_help": "Use the staff account created by an administrator in Admin CRM.",
    })


@router.post("/staff/login")
def staff_login(request: Request, username: str = Form(...), password: str = Form(...), _csrf: None = Depends(require_csrf)):
    request_key = client_key(request)
    context = {
        "request": request, "login_action": "/staff/login",
        "login_title": "Staff Login",
        "login_lead": "Sign in to register patients and manage QR redemptions.",
        "username_label": "Staff username",
        "username_placeholder": "Enter staff username",
        "login_help": "Use the staff account created by an administrator in Admin CRM.",
    }
    if _is_rate_limited(request_key):
        return request.app.state.templates.TemplateResponse(request, "login.html", {
            **context, "error": "Too many login attempts. Try again later."
        }, status_code=429)
    identity = authenticate_staff(username, password)
    if identity:
        _clear_failures(request_key)
        request.session.clear()
        request.session["user"] = identity["username"]
        request.session["role"] = "staff"
        request.session["staff_user_id"] = identity["staff_user_id"]
        request.session["session_version"] = SESSION_VERSION
        return RedirectResponse("/staff/home", status_code=303)
    _record_failure(request_key)
    return request.app.state.templates.TemplateResponse(request, "login.html", {
        **context, "error": "Invalid staff username or password"
    })


@router.post("/staff/logout")
def staff_logout(request: Request, _csrf: None = Depends(require_csrf)):
    request.session.clear()
    return RedirectResponse("/staff/login", status_code=303)
