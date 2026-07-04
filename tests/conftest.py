"""Shared pytest fixtures for Daybook.

Sets up an isolated SQLite database file per test run, points the app
at it via environment variables, and wipes tables between tests so each
test starts from a clean state.
"""
from pathlib import Path
import os
import pytest

# Configure the app for testing BEFORE importing it. app.py reads these
# at module-load time.
_TEST_DB = Path(__file__).parent / "test_daybook.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB}"
os.environ["SECRET_KEY"] = "testing-secret-not-a-real-key"

from app import app as flask_app, db  # noqa: E402  (must come after env setup)


@pytest.fixture(scope="session")
def app():
    """Session-wide app + tables. Wipe the file at the very end.

    IMPORTANT: we do NOT keep an app_context pushed across the yield.
    A long-lived context makes `flask.g` outlive individual requests,
    which lets Flask-Login's cached `g._login_user` leak between tests
    (a fresh client would appear "already logged in" from the last test).
    Only push the context when we actually need it (setup / teardown).
    """
    flask_app.config.update(
        TESTING=True,
        # Skip CSRF in tests; forms don't have easy access to the token.
        # (Production still enforces it — controlled by Flask-WTF's default.)
        WTF_CSRF_ENABLED=False,
    )
    with flask_app.app_context():
        db.create_all()
    yield flask_app
    with flask_app.app_context():
        db.session.remove()
        db.drop_all()
    if _TEST_DB.exists():
        _TEST_DB.unlink()


@pytest.fixture
def client(app):
    """A fresh test client for each test — separate cookies/session."""
    return app.test_client()


@pytest.fixture(autouse=True)
def _reset_db(app):
    """Full drop_all + create_all between tests.
    Slower than truncating rows, but guarantees the SQLAlchemy session
    (identity map, pending changes) is torn down cleanly so no state
    leaks into the next test. For a suite of ~15 tests this is still
    under a second total.
    """
    yield
    with app.app_context():
        db.session.rollback()
        db.session.remove()
        db.drop_all()
        db.create_all()


# ---------- Small helpers used by multiple test files ----------

def register(client, username="alice", password="testpass123"):
    return client.post("/register", data={
        "username": username, "password": password,
    })


def login(client, username="alice", password="testpass123"):
    return client.post("/login", data={
        "username": username, "password": password,
    })


def logout(client):
    return client.post("/logout")


def add_task(client, content="a task"):
    return client.post("/", data={"content": content})