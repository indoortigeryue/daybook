# Imports
import os
from flask import Flask, render_template, url_for, request, redirect
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_wtf.csrf import CSRFProtect
from datetime import datetime, timezone

# My app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
# SECRET_KEY is used by Flask to sign CSRF tokens (and session cookies).
# In production, set this via environment variable — never commit a real secret.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-only-insecure-key-change-me')
db = SQLAlchemy(app)
migrate = Migrate(app, db)
csrf = CSRFProtect(app)

class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(200), nullable=False)
    completed = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=db.text('0'),  # backfills existing rows during ALTER TABLE
    )
    completed_at = db.Column(db.DateTime, nullable=True)  # UTC; null when incomplete
    date_created = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return "<Task %r>" % self.id

@app.route("/", methods=["POST", "GET"])
def index():
    if request.method == "POST":
        task_content = request.form['content']
        new_task = Todo(content=task_content)

        try:
            db.session.add(new_task)
            db.session.commit()
            return redirect('/')
        except Exception as e:
            db.session.rollback()
            app.logger.exception("Failed to add task")
            return f'There was an issue adding your task: {e}', 500
    else:
        # Incomplete tasks first (False=0 sorts before True=1), then by date
        tasks = Todo.query.order_by(Todo.completed, Todo.date_created).all()
        return render_template("index.html", tasks=tasks)

@app.route('/toggle/<int:id>', methods=['POST'])
def toggle(id):
    task = Todo.query.get_or_404(id)
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
def delete(id):
    task_to_delete = Todo.query.get_or_404(id)

    try:
        db.session.delete(task_to_delete)
        db.session.commit()
        return redirect('/')
    except Exception as e:
        db.session.rollback()
        app.logger.exception("Failed to delete task id=%s", id)
        return f'There was a problem deleting that task: {e}', 500

@app.route('/update/<int:id>', methods=['GET', 'POST'])
def update(id):
    task = Todo.query.get_or_404(id)

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
    # Schema is managed by Flask-Migrate.
    # Run `flask db upgrade` once after cloning / after pulling migrations,
    # then `python app.py` to start the server.
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=True, port=port)