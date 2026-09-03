import secrets
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from threading import Lock

from fastapi import Form, HTTPException, Request


CSRF_SESSION_KEY = "csrf_token"
_attempts = defaultdict(deque)
_attempts_lock = Lock()


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def is_rate_limited(scope: str, key: str, maximum: int, window: timedelta) -> bool:
    """Return whether a scoped in-memory sliding window has reached its limit."""
    now = datetime.now(timezone.utc)
    bucket = (scope, key)
    with _attempts_lock:
        attempts = _attempts[bucket]
        while attempts and now - attempts[0] > window:
            attempts.popleft()
        return len(attempts) >= maximum


def record_rate_limit_event(scope: str, key: str) -> None:
    with _attempts_lock:
        _attempts[(scope, key)].append(datetime.now(timezone.utc))


def clear_rate_limit_events(scope: str, key: str) -> None:
    with _attempts_lock:
        _attempts.pop((scope, key), None)


def get_csrf_token(request: Request) -> str:
    token = request.session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token
    return token


def require_csrf(request: Request, csrf_token: str | None = Form(None, alias="_csrf_token")) -> None:
    expected = request.session.get(CSRF_SESSION_KEY)
    if not expected or not csrf_token or not secrets.compare_digest(expected, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid or expired form submission")


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"content-security-policy", b"default-src 'self'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; img-src 'self' data:; script-src 'self' 'unsafe-inline' https://unpkg.com; style-src 'self'; connect-src 'self'"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"permissions-policy", b"camera=(self), geolocation=(), microphone=()"),
                    (b"cache-control", b"no-store"),
                ])
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)
