from flask import Flask, render_template_string, request, redirect, url_for, flash, session
from datetime import datetime, date, timedelta
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "change-this-secret-key"  # needed for login sessions

DB_PATH = "prison_visits.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            visit_date DATE NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            created_at DATETIME NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def next_saturdays(n=8):
    today = date.today()
    days_ahead = (5 - today.weekday()) % 7  # Saturday = 5
    first_sat = today + timedelta(days=days_ahead)
    sats = []
    d = first_sat
    for _ in range(n):
        sats.append(d)
        d += timedelta(days=7)
    return sats


# ---------------------------
# ADMIN LOGIN
# ---------------------------
@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == os.environ.get("ADMIN_PASSWORD"):
            session["admin"] = True
            return redirect(url_for("admin"))
        else:
            flash(("error", "Incorrect password."))
            return redirect(url_for("admin_login"))

    template = """
    <!doctype html>
    <html>
    <body style="font-family: sans-serif; max-width: 400px; margin: 40px auto;">
        <h2>Admin Login</h2>
        <form method="post">
            <label>Password
                <input type="password" name="password" style="width:100%; padding:6px;">
            </label>
            <button style="margin-top:15px;">Login</button>
        </form>
        <p><a href="/">← Back</a></p>
    </body>
    </html>
    """
    return render_template_string(template)


@app.route("/logout")
def logout():
    session.pop("admin", None)
    return redirect(url_for("index"))


# ---------------------------
# PUBLIC BOOKING PAGE
# ---------------------------
@app.route("/")
def index():
    conn = get_db()
    c = conn.cursor()

    sats = next_saturdays()

    bookings_per_day = {}
    for d in sats:
        c.execute("SELECT COUNT(*) as cnt FROM bookings WHERE visit_date = ?", (d.isoformat(),))
        bookings_per_day[d] = c.fetchone()["cnt"]

    conn.close()

    template = """
    <!doctype html>
    <html>
    <head>
        <title>Prison Visit Booking</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: sans-serif; max-width: 700px; margin: 20px auto; padding: 0 10px; }
            .date-card { border: 1px solid #ccc; border-radius: 8px; padding: 10px 15px; margin-bottom: 10px; }
            .full { background: #f8d7da; }
            .available { background: #d4edda; }
            .btn { padding: 6px 12px; border-radius: 4px; border: none; cursor: pointer; }
            .btn-primary { background: #007bff; color: white; }
            .btn-disabled { background: #aaa; color: #eee; cursor: not-allowed; }
            .flash { padding: 8px 10px; border-radius: 4px; margin-bottom: 10px; }
        </style>
    </head>
    <body>
        <h1>Book a Visit</h1>
        <p>Choose a Saturday. Max 2 visitors per day.</p>

        {% for d, count in days %}
            <div class="date-card {% if count >= 2 %}full{% else %}available{% endif %}">
                <strong>{{ d.strftime("%A %d %B %Y") }}</strong><br>
                Booked: {{ count }}/2
                <div style="margin-top:8px;">
                {% if count < 2 %}
                    <form method="get" action="{{ url_for('book') }}" style="display:inline;">
                        <input type="hidden" name="date" value="{{ d.isoformat() }}">
                        <button class="btn btn-primary" type="submit">Book</button>
                    </form>
                {% else %}
                    <button class="btn btn-disabled" disabled>Full</button>
                {% endif %}
                </div>
            </div>
        {% endfor %}

        <p><a href="{{ url_for('admin_login') }}">Admin</a></p>
    </body>
    </html>
    """
    return render_template_string(template, days=list(bookings_per_day.items()))


# ---------------------------
# BOOKING FORM
# ---------------------------
@app.route("/book", methods=["GET", "POST"])
def book():
    if request.method == "GET":
        visit_date_str = request.args.get("date")
    else:
        visit_date_str = request.form.get("visit_date")

    if not visit_date_str:
        flash(("error", "No date selected."))
        return redirect(url_for("index"))

    try:
        visit_date = datetime.strptime(visit_date_str, "%Y-%m-%d").date()
    except ValueError:
        flash(("error", "Invalid date."))
        return redirect(url_for("index"))

    if visit_date.weekday() != 5:
        flash(("error", "Only Saturdays allowed."))
        return redirect(url_for("index"))

    if visit_date < date.today():
        flash(("error", "Cannot book past dates."))
        return redirect(url_for("index"))

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM bookings WHERE visit_date = ?", (visit_date.isoformat(),))
    booked = c.fetchone()["cnt"]

    if booked >= 2:
        conn.close()
        flash(("error", "This day is full."))
        return redirect(url_for("index"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()

        if not name or not email:
            flash(("error", "Fill all fields."))
            conn.close()
            return redirect(url_for("book") + f"?date={visit_date_str}")

        c.execute(
            "INSERT INTO bookings (visit_date, name, email, created_at) VALUES (?, ?, ?, ?)",
            (visit_date.isoformat(), name, email, datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
        flash(("success", "Your visit has been booked."))
        return redirect(url_for("index"))

    template = """
    <!doctype html>
    <html>
    <body style="font-family: sans-serif; max-width: 600px; margin: 20px auto;">
        <h2>Book for {{ visit_date.strftime("%A %d %B %Y") }}</h2>
        <form method="post">
            <input type="hidden" name="visit_date" value="{{ visit_date.isoformat() }}">
            <label>Name
                <input type="text" name="name" required>
            </label>
            <label>Email
                <input type="email" name="email" required>
            </label>
            <button style="margin-top:10px;">Confirm</button>
        </form>
        <p><a href="/">← Back</a></p>
    </body>
    </html>
    """
    conn.close()
    return render_template_string(template, visit_date=visit_date)


# ---------------------------
# ADMIN PAGE (PROTECTED)
# ---------------------------
@app.route("/admin")
def admin():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM bookings ORDER BY visit_date, created_at")
    rows = c.fetchall()
    conn.close()

    template = """
    <!doctype html>
    <html>
    <body style="font-family: sans-serif; max-width: 800px; margin: 20px auto;">
        <h1>All bookings</h1>
        <p><a href="{{ url_for('logout') }}">Logout</a></p>
        <table border="1" cellpadding="6">
            <tr>
                <th>Date</th><th>Name</th><th>Email</th><th>Booked at (UTC)</th>
            </tr>
            {% for r in rows %}
            <tr>
                <td>{{ r["visit_date"] }}</td>
                <td>{{ r["name"] }}</td>
                <td>{{ r["email"] }}</td>
                <td>{{ r["created_at"] }}</td>
            </tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """
    return render_template_string(template, rows=rows)


# ---------------------------
# START APP
# ---------------------------
if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_db()
    else:
        init_db()
    app.run(debug=True)
