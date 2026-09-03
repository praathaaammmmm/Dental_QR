from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from .config import DATABASE_URL, DB_MAX_OVERFLOW, DB_POOL_SIZE, DB_POOL_TIMEOUT_SECONDS

if DATABASE_URL.startswith("sqlite"):
    engine_options = {"connect_args": {"check_same_thread": False}}
else:
    engine_options = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_size": DB_POOL_SIZE,
        "max_overflow": DB_MAX_OVERFLOW,
        "pool_timeout": DB_POOL_TIMEOUT_SECONDS,
    }

engine = create_engine(DATABASE_URL, future=True, **engine_options)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

class Base(DeclarativeBase):
    pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
