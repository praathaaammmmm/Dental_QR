"""Regression coverage for the Alembic migration chain itself.

The rest of the suite builds its schema with `Base.metadata.create_all`, which never
exercises the migration files, so a broken migration (wrong batch mode, a dialect-specific
literal, etc.) can ship unnoticed. These tests actually invoke `alembic upgrade head` /
`downgrade base` in a subprocess against scratch databases to catch that class of bug.

The SQLite run is unconditional. A Postgres run only happens when TEST_POSTGRES_URL is set
(e.g. `postgresql+psycopg://postgres:test@localhost:55432/migtest`) since most local/dev
environments don't have a Postgres server available — this is where the real bug this file
guards against (a batch `recreate="always"` trying to drop `patient_offers_pkey` while
`delivery_logs`/`audit_logs` foreign keys still reference it) actually reproduces; SQLite's
batch mode never hits it.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _run_alembic(*args, database_url):
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"alembic {' '.join(args)} failed against {database_url!r}\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return result


def test_full_migration_chain_upgrades_and_downgrades_on_sqlite(tmp_path):
    db_path = tmp_path / "migration_chain_test.db"
    database_url = f"sqlite:///{db_path}"
    _run_alembic("upgrade", "head", database_url=database_url)
    _run_alembic("downgrade", "base", database_url=database_url)


@pytest.mark.skipif(
    not os.getenv("TEST_POSTGRES_URL"),
    reason="set TEST_POSTGRES_URL to a scratch Postgres database to run this check",
)
def test_full_migration_chain_upgrades_and_downgrades_on_postgres():
    database_url = os.environ["TEST_POSTGRES_URL"]
    _run_alembic("upgrade", "head", database_url=database_url)
    _run_alembic("downgrade", "base", database_url=database_url)
