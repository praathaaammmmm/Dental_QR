import os
import re
from argon2 import PasswordHasher
os.environ["APP_ENV"] = "test"
os.environ["CLINIC_USERNAME"] = "smritiraj-clinic"
os.environ["CLINIC_PASSWORD_HASH"] = PasswordHasher().hash("test-password")
os.environ["SESSION_SECRET_KEY"] = "test-session-secret-that-is-long-enough"
os.environ["SESSION_HTTPS_ONLY"] = "false"
os.environ["DATABASE_URL"] = "sqlite:///./test_smritiraj.db"
from fastapi.testclient import TestClient
from app.main import app
from app.database import Base, engine
import pytest

CSRF_PATTERN = re.compile(r'name="_csrf_token" value="([^"]+)"')


class CSRFTestClient(TestClient):
    def post(self, url, *, include_csrf=True, data=None, **kwargs):
        if include_csrf:
            page = super().get("/login", follow_redirects=True)
            match = CSRF_PATTERN.search(page.text)
            if not match:
                raise AssertionError("CSRF token was not rendered")
            data = dict(data or {})
            data.setdefault("_csrf_token", match.group(1))
        return super().post(url, data=data, **kwargs)

@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    from app.database import SessionLocal
    from app.models import Offer
    db = SessionLocal()
    db.add_all([
        Offer(name="Free In-House Zirconia Crown", description="test"),
        Offer(name="Free In-House Aligner Scan", description="test"),
    ])
    db.commit(); db.close()
    with CSRFTestClient(app) as c:
        c.post("/login", data={"username":"smritiraj-clinic", "password":"test-password"})
        yield c
    Base.metadata.drop_all(bind=engine)
