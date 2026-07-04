# Imports
import os
import secrets
from itertools import groupby
from flask import Flask, render_template, url_for, request, redirect, session
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user,
)
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone, timedelta

# ---- Configuration --------------------------------------------------------
# Everything env-driven; the same code runs SQLite locally and Postgres on
# a cloud host. See 12-Factor App III (Config) & IV (Backing services).

# DATABASE_URL: cloud providers (Neon, Render, Heroku) inject this at runtime.
# Fall back to SQLite for local dev.
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///test.db')
# Legacy 'postgres://' scheme (Heroku era) isn't recognized by SQLAlchemy 2.x.
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

# Presence of DATABASE_URL is a reliable "we're deployed" signal
IS_PRODUCTION = bool(os.environ.get('DATABASE_URL'))

# SECRET_KEY: required in prod (used to sign session cookies + CSRF tokens).
# Refusing to start without it is safer than silently using a known-weak key.
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    if IS_PRODUCTION:
        raise RuntimeError(
            'SECRET_KEY env var must be set in production. '
            'Generate one with: python -c "import secrets; print(secrets.token_hex(32))"'
        )
    SECRET_KEY = 'dev-only-insecure-key-change-me'

app = Flask(__name__)
app.config.update(
    SQLALCHEMY_DATABASE_URI=DATABASE_URL,
    SECRET_KEY=SECRET_KEY,
    # Serverless Postgres (Neon) closes idle connections; ping before use to
    # detect stale pooled connections and reconnect transparently.
    SQLALCHEMY_ENGINE_OPTIONS={'pool_pre_ping': True},
    # ---- Session cookie hardening ----
    SESSION_COOKIE_HTTPONLY=True,      # JS can't read (defense against XSS)
    SESSION_COOKIE_SAMESITE='Lax',     # Extra CSRF defense (defense in depth)
    SESSION_COOKIE_SECURE=IS_PRODUCTION,  # HTTPS-only in prod; false locally so cookies work over http
)
db = SQLAlchemy(app)
migrate = Migrate(app, db)
csrf = CSRFProtect(app)
login_manager = LoginManager(app)
# Where to redirect unauthenticated users hitting @login_required routes
login_manager.login_view = 'login'
login_manager.login_message = None  # Suppress default "Please log in" flash

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_guest = db.Column(db.Boolean, nullable=False, default=False,
                        server_default=db.false())
    created_at = db.Column(db.DateTime,
                          default=lambda: datetime.now(timezone.utc))

    tasks = db.relationship('Todo', backref='user', lazy='dynamic',
                           cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.username!r}>"


@login_manager.user_loader
def load_user(user_id):
    """Given the id stored in the session, return the User object.
    Flask-Login calls this on every request to hydrate `current_user`."""
    return User.query.get(int(user_id))


class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'),
                       nullable=False, index=True)
    content = db.Column(db.String(200), nullable=False)
    completed = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=db.false(),  # backfills existing rows; dialect-neutral (0 on SQLite, FALSE on Postgres)
    )
    completed_at = db.Column(db.DateTime, nullable=True)  # UTC; null when incomplete
    date_created = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return "<Task %r>" % self.id


# ---- Auth routes ------------------------------------------------------------

def _safe_next(next_url):
    """Return next_url only if it's a same-origin relative path.
    Prevents open-redirect vulnerabilities where an attacker crafts
    a login link like /login?next=https://evil.com."""
    if next_url and next_url.startswith('/') and not next_url.startswith('//'):
        return next_url
    return None

def _clear_user_scoped_session():
    """Wipe session keys that belong to the *previous* user.
    Session cookies follow the browser, not the account — so on any
    login boundary we must reset per-user state (e.g. "have you seen
    today's journal?"). Otherwise state leaks across accounts."""
    for key in ('last_journal_date', 'welcomed'):
        session.pop(key, None)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect('/')
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        error = None
        if not username or not password:
            error = 'Username and password are required.'
        elif len(username) < 3:
            error = 'Username must be at least 3 characters.'
        elif len(password) < 6:
            error = 'Password must be at least 6 characters.'
        elif User.query.filter_by(username=username).first():
            error = 'That username is already taken.'
        if error:
            return render_template('register.html', error=error,
                                   username=username), 400
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        _clear_user_scoped_session()
        login_user(user)
        return redirect('/')
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect('/')
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            _clear_user_scoped_session()
            login_user(user)
            return redirect(_safe_next(request.args.get('next')) or '/')
        return render_template('login.html',
                               error='Invalid username or password.',
                               username=username), 401
    return render_template('login.html')

@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    _clear_user_scoped_session()
    return redirect('/login')

def _seed_guest_tasks(user_id):
    """Populate the guest account with a curated set of tasks that
    show off every feature: today's completed, incomplete carryovers,
    yesterday's completions (fuels morning reflection), and archive
    entries from earlier days."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    two_days_ago = now - timedelta(days=2)
    yesterday = now - timedelta(days=1)
    today_9am = now.replace(hour=9, minute=15, second=0, microsecond=0)
    today_2pm = now.replace(hour=14, minute=30, second=0, microsecond=0)

    seed = [
        # Archive — completed on prior days (shows in /archive)
        (two_days_ago, two_days_ago, True, 'Draft product spec'),
        (two_days_ago, two_days_ago, True, 'Ship Alembic migration'),
        # Yesterday's completions (feeds morning reflection)
        (yesterday, yesterday, True, 'Review PR #47'),
        (yesterday, yesterday, True, 'Send follow-up email'),
        # Carryovers — created earlier, still incomplete
        (yesterday, None, False, 'Book dentist appointment'),
        (two_days_ago, None, False, 'Read Alembic docs'),
        # Today's completed (stays on main list, not archive)
        (today_9am, today_9am, True, 'Morning standup notes'),
        # Today's incomplete
        (today_9am, None, False, "Write today's blog post"),
        (today_2pm, None, False, 'Plan sprint retro'),
    ]
    for date_created, completed_at, completed, content in seed:
        db.session.add(Todo(
            user_id=user_id, content=content,
            completed=completed, completed_at=completed_at,
            date_created=date_created,
        ))

@app.route('/guest-login', methods=['POST'])
def guest_login():
    """One-click demo access for anyone visiting the portfolio site.
    Wipes and reseeds sample tasks on every visit so recruiters
    always see a fully-populated demo, no matter what previous
    guests did."""
    if current_user.is_authenticated:
        return redirect('/')
    guest = User.query.filter_by(username='guest', is_guest=True).first()
    if not guest:
        guest = User(username='guest', is_guest=True)
        # Random unusable password — guest login only happens via this route,
        # never through the normal password form.
        guest.set_password(secrets.token_urlsafe(32))
        db.session.add(guest)
        db.session.flush()  # Assign guest.id before we seed FK-linked tasks
    else:
        Todo.query.filter_by(user_id=guest.id).delete()
    _seed_guest_tasks(guest.id)
    db.session.commit()
    _clear_user_scoped_session()
    login_user(guest)
    return redirect('/')


# ---- Task routes ------------------------------------------------------------

@app.route("/", methods=["POST", "GET"])
@login_required
def index():
    if request.method == "POST":
        task_content = request.form['content']
        new_task = Todo(content=task_content, user_id=current_user.id)

        try:
            db.session.add(new_task)
            db.session.commit()
            return redirect('/')
        except Exception as e:
            db.session.rollback()
            app.logger.exception("Failed to add task")
            return f'There was an issue adding your task: {e}', 500
    else:
        # Today's boundary in UTC (matches how completed_at / date_created are stored)
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=None
        )

        # Main list: incomplete tasks + tasks completed TODAY.
        # Older completed tasks are moved to the /archive view.
        # Every task query filters by current_user — no data leaks across users.
        tasks = Todo.query.filter(
            Todo.user_id == current_user.id,
            db.or_(
                Todo.completed.is_(False),
                Todo.completed_at >= today_start,
            )
        ).order_by(Todo.completed, Todo.date_created).all()

        # Count of tasks in the archive, for the "View past tasks (N)" link
        archive_count = Todo.query.filter(
            Todo.user_id == current_user.id,
            Todo.completed.is_(True),
            Todo.completed_at < today_start,
        ).count()

        now = datetime.now()
        today = f"{now.strftime('%A, %B')} {now.day}, {now.year}"

        # ---- Welcome modal for brand-new users ----
        # A user is "new" if they haven't dismissed welcome AND have zero tasks
        # AND isn't the shared guest account (guests should see the full demo,
        # not an onboarding message).
        show_welcome = (
            not current_user.is_guest
            and session.get('welcomed') != 'y'
            and Todo.query.filter_by(user_id=current_user.id).count() == 0
        )

        # ---- Daily journal: show once per day on first visit ----
        # Skipped when welcome modal is showing — one modal at a time.
        today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        show_journal = (
            not show_welcome
            and session.get('last_journal_date') != today_str
        )

        journal = None
        if show_journal:
            today_start = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0, tzinfo=None
            )
            yesterday_start = today_start - timedelta(days=1)

            yesterday_done = Todo.query.filter(
                Todo.user_id == current_user.id,
                Todo.completed.is_(True),
                Todo.completed_at >= yesterday_start,
                Todo.completed_at < today_start,
            ).order_by(Todo.completed_at).all()

            carryovers = Todo.query.filter(
                Todo.user_id == current_user.id,
                Todo.completed.is_(False),
                Todo.date_created < today_start,
            ).order_by(Todo.date_created).all()

            journal = {
                'yesterday_done': yesterday_done,
                'carryovers': carryovers,
            }
            # Note: session is marked as seen only when the user explicitly
            # dismisses via POST /journal/dismiss — not on mere page render.

        return render_template(
            "index.html",
            tasks=tasks,
            today=today,
            journal=journal,
            welcome=show_welcome,
            archive_count=archive_count,
        )

@app.route('/archive')
@login_required
def archive():
    """Show all previously completed tasks, grouped by completion date."""
    today_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0, tzinfo=None
    )
    tasks = Todo.query.filter(
        Todo.user_id == current_user.id,
        Todo.completed.is_(True),
        Todo.completed_at < today_start,
    ).order_by(Todo.completed_at.desc()).all()

    # Group by date (already sorted DESC, so groupby produces desc-date groups)
    grouped = [
        (day, list(items))
        for day, items in groupby(tasks, key=lambda t: t.completed_at.date())
    ]
    return render_template("archive.html", grouped=grouped, total=len(tasks))

@app.route('/journal/dismiss', methods=['POST'])
@login_required
def journal_dismiss():
    """Mark today's morning reflection as seen. Called when user clicks 'Start my day'."""
    today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    session['last_journal_date'] = today_str
    return redirect('/')

@app.route('/welcome/dismiss', methods=['POST'])
@login_required
def welcome_dismiss():
    """Mark the welcome modal as seen for this browser session.
    Also mark today's morning reflection as seen — a brand-new user has
    no history to reflect on, and stacking two modals back-to-back is
    overwhelming."""
    session['welcomed'] = 'y'
    session['last_journal_date'] = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    return redirect('/')


def _get_own_task_or_404(task_id):
    """Fetch a task belonging to current_user, or 404 otherwise.
    Uses filter_by(user_id=...) instead of just get() to prevent IDOR —
    even if Alice guesses Bob's task id, she gets a 404, not Bob's data."""
    return Todo.query.filter_by(
        id=task_id, user_id=current_user.id
    ).first_or_404()

@app.route('/toggle/<int:id>', methods=['POST'])
@login_required
def toggle(id):
    task = _get_own_task_or_404(id)
    task.completed = not task.completed
    task.completed_at = datetime.now(timezone.utc) if task.completed else None
    try:
        db.session.commit()
        return redirect('/')
    except Exception as e:
        db.session.rollback()
        app.logger.exception("Failed to toggle task id=%s", id)
        return f'There was an issue toggling that task: {e}', 500

@app.route('/delete/<int:id>', methods=['POST'])
@login_required
def delete(id):
    task_to_delete = _get_own_task_or_404(id)

    try:
        db.session.delete(task_to_delete)
        db.session.commit()
        return redirect('/')
    except Exception as e:
        db.session.rollback()
        app.logger.exception("Failed to delete task id=%s", id)
        return f'There was a problem deleting that task: {e}', 500

@app.route('/update/<int:id>', methods=['GET', 'POST'])
@login_required
def update(id):
    task = _get_own_task_or_404(id)

    if request.method == 'POST':
        task.content = request.form['content']

        try:
            db.session.commit()
            return redirect('/')
        except Exception as e:
            db.session.rollback()
            app.logger.exception("Failed to update task id=%s", id)
            return f'There was an issue updating your task: {e}', 500
    else:
        return render_template('update.html', task=task)


if __name__ == "__main__":
    # NOTE: In production this block is NOT executed. Gunicorn imports
    # `app` directly (see Procfile: `web: gunicorn app:app`) and serves
    # WSGI without touching __main__. Debug is only relevant locally.
    #
    # Schema is managed by Flask-Migrate — run `flask db upgrade` once
    # after cloning / after pulling migrations, then `python app.py`.
    port = int(os.environ.get('PORT', 5001))
    # Default debug=ON locally; explicitly disable with FLASK_DEBUG=0
    debug = os.environ.get('FLASK_DEBUG', '1') != '0'
    app.run(debug=debug, port=port)