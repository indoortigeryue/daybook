"""Task CRUD + data isolation between users (IDOR protection).

Anyone who can guess another user's task id must NOT be able to read,
toggle, edit, or delete it — this is the OWASP "Broken Access Control"
class of vulnerability, and it's the security signal I most want a
reviewer to notice.
"""
import pytest
from app import Todo, db
from tests.conftest import register, logout, add_task


def test_signed_in_user_can_add_and_see_a_task(client, app):
    register(client, "alice")
    add_task(client, "buy milk")
    r = client.get("/")
    assert b"buy milk" in r.data


def test_toggle_flips_completion(client, app):
    register(client, "alice")
    add_task(client, "toggle me")
    with app.app_context():
        task = Todo.query.filter_by(content="toggle me").first()
        task_id = task.id
        assert task.completed is False

    client.post(f"/toggle/{task_id}")

    with app.app_context():
        task = db.session.get(Todo,task_id)
        assert task.completed is True
        assert task.completed_at is not None


def test_delete_removes_the_task(client, app):
    register(client, "alice")
    add_task(client, "delete me")
    with app.app_context():
        task_id = Todo.query.filter_by(content="delete me").first().id

    client.post(f"/delete/{task_id}")

    with app.app_context():
        assert db.session.get(Todo,task_id) is None


# ---- IDOR (data isolation) — the security-critical tests ----

def test_users_cannot_see_each_others_tasks(client, app):
    register(client, "alice")
    add_task(client, "alice-private-task")
    logout(client)

    register(client, "bob")
    r = client.get("/")
    assert b"alice-private-task" not in r.data


@pytest.mark.parametrize("verb,path_fmt", [
    ("POST", "/toggle/{}"),
    ("POST", "/delete/{}"),
    ("GET",  "/update/{}"),
])
def test_users_cannot_touch_each_others_tasks(client, app, verb, path_fmt):
    """A signed-in user who guesses another user's task id gets 404,
    not the other user's data. Applies to toggle, delete, and update."""
    register(client, "alice")
    add_task(client, "alice-secret")
    with app.app_context():
        alice_task_id = Todo.query.filter_by(content="alice-secret").first().id
    logout(client)

    register(client, "bob")
    path = path_fmt.format(alice_task_id)
    r = client.get(path) if verb == "GET" else client.post(path)
    assert r.status_code == 404

    # Alice's task must be untouched
    with app.app_context():
        alice_task = db.session.get(Todo,alice_task_id)
        assert alice_task is not None
        assert alice_task.completed is False
        assert alice_task.content == "alice-secret"