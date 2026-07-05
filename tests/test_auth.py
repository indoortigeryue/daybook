"""Registration, login, logout, and guest access."""
from tests.conftest import register, login, logout


def test_anonymous_home_redirects_to_login(client):
    r = client.get("/")
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_register_creates_user_and_signs_them_in(client):
    r = register(client, "alice")
    assert r.status_code == 302
    assert r.headers["Location"] == "/"
    # Follow the redirect — should now be on the app page, not the login page
    r = client.get("/")
    assert r.status_code == 200
    assert b"alice" in r.data


def test_register_rejects_duplicate_username(client):
    register(client, "bob")
    logout(client)
    r = register(client, "bob", password="another")
    assert r.status_code == 400
    assert b"already taken" in r.data


def test_register_rejects_short_password(client):
    r = register(client, "carol", password="abc")
    assert r.status_code == 400


def test_login_with_correct_credentials(client):
    register(client, "dave")
    logout(client)
    r = login(client, "dave")
    assert r.status_code == 302
    assert r.headers["Location"] == "/"


def test_login_with_wrong_password_fails(client):
    register(client, "eve")
    logout(client)
    r = login(client, "eve", password="not-my-password")
    assert r.status_code == 401


def test_login_with_nonexistent_user_fails(client):
    r = login(client, "nobody", password="whatever")
    assert r.status_code == 401


def test_guest_login_creates_a_seeded_account(client):
    r = client.post("/guest-login")
    assert r.status_code == 302
    # Guest should see sample content on the main page
    r = client.get("/")
    assert r.status_code == 200
    assert b"guest" in r.data
    # Guest gets 9 seeded tasks — at least a few should be visible
    body = r.data.decode()
    assert any(name in body for name in [
        "Morning standup", "Book dentist", "Read Alembic",
    ])


def test_demo_landing_clears_session_and_redirects_to_login(client):
    """The /demo entry point (advertised on the resume) always drops
    the current session so a stale guest cookie doesn't skip past the
    branded login page."""
    # Log in as guest first, then hit /demo
    client.post("/guest-login")
    r = client.get("/demo", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]
    # After /demo, hitting / should redirect to login (not into the app)
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


def test_logout_signs_user_out(client):
    register(client, "frank")
    logout(client)
    # After logout, hitting / should redirect to login
    r = client.get("/")
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]