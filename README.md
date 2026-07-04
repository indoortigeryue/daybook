# Daybook

A quieter Flask journal for daily tasks and morning reflections.

**Live demo →** [daybook-qti8.onrender.com](https://daybook-qti8.onrender.com/)
Click **"Try as guest →"** on the sign-in page for one-click access with a
curated set of sample tasks. No registration required.

> Deployed on Render's free tier — the first request after ~15 minutes of
> idle takes about 30 seconds to wake up. Subsequent requests are instant.

<!-- Replace with an actual screenshot or short GIF:
     save one to docs/screenshot.png and drop it in below. -->

![Daybook screenshot](docs/screenshot.png)

---

## What it does

- **Capture** what's on your mind — one small task at a time.
- On your first visit each day, a **Morning Reflection** modal recaps
  yesterday's completions and surfaces anything you didn't finish.
- Older completed tasks slide into a **quiet archive**, grouped by
  date, so today's list stays focused on today.
- **Guest mode** reseeds a full sample dataset on every visit — great
  for demoing the app without leaving artifacts.

## Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.11+ |
| Web framework | Flask 3 + Jinja2 |
| ORM & migrations | SQLAlchemy 2 + Alembic (via Flask-Migrate) |
| Auth | Flask-Login + Werkzeug password hashing (pbkdf2-sha256) |
| CSRF | Flask-WTF |
| Database | Postgres 18 in production (Neon), SQLite locally |
| Server | Gunicorn on Render |
| Frontend | Vanilla CSS, no build step, no framework |

---

## Notable engineering choices

This project is a personal learning piece, but I've written it as though
someone else will read the code. The decisions below are the ones a
beginner CRUD tutorial usually skips.

### Auth and access control

- **Password hashing** via `werkzeug.security` (pbkdf2-sha256 by default,
  auto-salted). No plaintext passwords anywhere.
- **IDOR protection**: every task-scoped query filters by
  `current_user.id`. A signed-in user who guesses another user's task
  id gets a 404, not their data. See `_get_own_task_or_404` in `app.py`.
- **CSRF protection** on every state-changing route via Flask-WTF.
  Both form-body `csrf_token` and `X-CSRFToken` header are accepted, so
  progressive-enhancement `fetch()` calls work alongside plain forms.
- **Session cookies** are `HttpOnly`, `SameSite=Lax` always, and
  `Secure` in production (auto-detected from `DATABASE_URL`).
- **Open-redirect defense** on the `?next=` parameter (`_safe_next`
  rejects anything that isn't a same-origin relative path).
- **Fail-loud on missing secrets**: the app refuses to start in
  production without an explicit `SECRET_KEY`. No silent fallback to a
  dev key.
- **Per-user session hygiene**: session-cookie state that is user-scoped
  (like "have you dismissed today's journal?") is cleared at every
  login boundary. Prevents state leaking across accounts on shared
  browsers.

### Schema and migrations

- **No `db.create_all()`** — schema changes go through Alembic. Every
  change is a versioned, reviewable migration file.
- **Dialect-neutral defaults** (`sa.false()`, not `sa.text('0')`) so
  the same migration runs on SQLite locally and Postgres in prod.
  This was the actual bug that surfaced on first deploy.
- **Named FK constraints** — required by SQLite's batch-mode migrations.
- **`pool_pre_ping=True`** on the SQLAlchemy engine in production, so
  connections idled by Neon's serverless Postgres are re-validated
  before use.
- **Boolean `server_default`** ensures existing rows get a valid value
  when `NOT NULL` columns are added mid-project.

### Config and deployment

- **Twelve-Factor App**: `DATABASE_URL`, `SECRET_KEY`, and `PORT` all
  come from the environment. The same code runs SQLite locally and
  Postgres in production with no code change.
- Legacy `postgres://` URL scheme (Heroku/Neon default) is rewritten
  to `postgresql://` so SQLAlchemy 2.x accepts it.
- **Migrations run on release**, not on build. The Render start
  command is `flask db upgrade && gunicorn app:app` so every deploy
  applies any pending schema changes before serving traffic.

### UX and frontend

- **Zero-JavaScript baseline**: every form posts to a real endpoint and
  works without JS. JavaScript is layered on top only to smooth
  modal open/close animations.
- **Newspaper-unfold animation** on the Morning Reflection modal
  (two-phase `scale()` keyframes — first horizontal stretch, then
  vertical unfold).
- **`prefers-reduced-motion`** collapses all animations for users who
  request reduced motion in their OS.
- **`text-wrap: pretty`** prevents widow words on paragraph text,
  with a manual `&nbsp;` as a fallback for older browsers.
- **Serif + sans-serif pairing** (Playfair Display for display type,
  system sans for body) modeled on editorial design (New Yorker,
  Medium).
- **Guest mode reseeds** a curated dataset on every login. Reviewers
  always see the app in all states (archive with history, carryovers,
  yesterday's wins) without having to add data themselves.

---

## Running locally

```bash
git clone https://github.com/indoortigeryue/daybook.git
cd daybook

python3 -m venv env
source env/bin/activate            # Windows: env\Scripts\activate

pip install -r requirements.txt

export FLASK_APP=app.py
flask db upgrade                   # Creates the SQLite database

python app.py
```

Open <http://127.0.0.1:5001> — register a new account, or click
**Try as guest →** for one-click access.

## Project layout

```
daybook/
├── app.py                  # Models + all routes in a single file
├── migrations/             # Alembic schema history
├── templates/              # Jinja2 templates
│   ├── base.html
│   ├── index.html          # Main task list + Morning Reflection + Welcome
│   ├── archive.html        # Past-completed tasks, grouped by day
│   ├── login.html
│   ├── register.html
│   └── update.html
├── static/css/main.css     # All styles
├── requirements.txt
└── Procfile                # web: gunicorn app:app  (Render / Heroku format)
```

## What's next

Rough backlog, in priority order:

- Unit and integration tests (pytest)
- Password reset flow via email
- Proper per-user timezones (server stores UTC; UI currently shows UTC
  dates too)
- Task tags and search
- Public share links for daily reflections