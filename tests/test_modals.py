"""Welcome + Morning Reflection modal logic.

These modals are session-based (client cookie), so they're the place
most likely to leak state across accounts. The tests here focus on:
  - New users see Welcome (not Morning Reflection)
  - Welcome dismissal also silences Morning Reflection for today
  - Session state doesn't survive an auth boundary (login/register)
"""
from tests.conftest import register, logout, add_task


def _get(client):
    return client.get("/").data.decode()


def test_new_user_sees_welcome_not_journal(client):
    register(client, "alice")
    body = _get(client)
    assert "welcome-overlay" in body
    assert "journal-overlay" not in body


def test_welcome_dismiss_also_silences_todays_journal(client):
    """After the first login, a brand-new user closes welcome and adds
    their first task. The redirect back to / must NOT surface the
    Morning Reflection — there's nothing to reflect on yet, and back-
    to-back modals are overwhelming.
    """
    register(client, "alice")
    client.post("/welcome/dismiss")
    add_task(client, "first task")

    body = _get(client)
    assert "welcome-overlay" not in body
    assert "journal-overlay" not in body


def test_returning_user_sees_journal(client):
    """A user who already has tasks (i.e. no welcome), and whose session
    hasn't seen today's journal yet, should see the Morning Reflection."""
    register(client, "alice")
    client.post("/welcome/dismiss")
    add_task(client, "some task")
    # Simulate returning tomorrow — clear session to reset the "seen today" marker
    with client.session_transaction() as sess:
        sess.pop("last_journal_date", None)

    body = _get(client)
    assert "journal-overlay" in body


def test_session_state_does_not_leak_across_users(client):
    """User A dismisses today's journal. User B (in the same browser)
    logs in — they must see their own journal for today, not inherit
    A's "already seen" marker. Regression test for a real bug we hit.
    """
    # User A: register, dismiss journal
    register(client, "alice")
    client.post("/welcome/dismiss")
    add_task(client, "alice-task")  # so alice is no longer "brand new"
    logout(client)

    # User B: register in the same client (same session cookie)
    register(client, "bob")
    # Bob is brand-new so should see WELCOME (not journal).
    # The bug we're guarding against: if session state leaked, welcome
    # would be suppressed and no modal would show at all.
    body = _get(client)
    assert "welcome-overlay" in body