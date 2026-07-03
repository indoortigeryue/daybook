# Imports
import os
from flask import Flask, render_template, url_for, request, redirect
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from datetime import datetime, timezone

# My app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
# SECRET_KEY is used by Flask to sign CSRF tokens (and session cookies).
# In production, set this via environment variable — never commit a real secret.
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-only-insecure-key-change-me')
db = SQLAlchemy(app)
csrf = CSRFProtect(app)

class Todo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(200), nullable=False)
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
        tasks = Todo.query.order_by(Todo.date_created).all()
        return render_template("index.html", tasks=tasks)

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
    with app.app_context():
        db.create_all()
    # PORT can be overridden via env var — required by most cloud platforms
    # (Heroku, Render, Railway all inject $PORT at runtime).
    port = int(os.environ.get('PORT', 5001))
    app.run(debug=True, port=port)