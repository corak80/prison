from flask import Flask, render_template_string, request, redirect, url_for, flash
from datetime import datetime, date, timedelta
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "change-this-secret-key"  # needed for flash messages
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
    """Return list of next n Saturdays as date objects."""
    today = date.today()
    # weekday(): Monday=0 ... Sunday=6
    days_ahead = (5 - today.weekday()) % 7  # Saturday = 5
    first_sat = today + timedelta(days=days_ahead)
    saturdays = []
    d = first_sat
    for _ in range(n):
        saturdays.append(d)
        d += timedelta(days=7)
    return saturdays


@app.route("/")
def index():
    conn = get_db()
    c = conn.cursor()

    sats = next_saturdays()

    # Get booking count for each Saturday
    bookings_per_day = {}
    for d in sats:
        c.execute("SELECT COUNT(*) as cnt FROM bookings WHERE visit_date = ?", (d.isoformat(),))
        bookings_per_day[d] = c.fetchone()["cnt"]

    conn.close()

    # Simple template inline for demo
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
            .flash-error { background: #f8d7da; }
            .flash-success { background: #d4edda; }
        </style>
    </head>
    <body>
        <h1>Book a Visit</h1>
        <p>Choose a Saturday and fill in your details. Max 2 visitors per Saturday.</p>

        {% with messages = get_flashed_messages(with_categories=true) %}
          {% if messages %}
            {% for category, msg in messages %}
              <div class="flash flash-{{ category }}">{{ msg }}</div>
            {% endfor %}
          {% endif %}
        {% endwith %}

        {% for d, count in days %}
            <div class="date-card {% if count >= 2 %}full{% else %}available{% endif %}">
                <strong>{{ d.strftime("%A %d %B %Y") }}</strong><br>
                Currently booked: {{ count }}/2
                <div style="margin-top:8px;">
                {% if count < 2 %}
                    <form method="get" action="{{ url_for('book') }}" style="display:inline;">
                        <input type="hidden" name="date" value="{{ d.isoformat() }}">
                        <button class="btn btn-primary" type="submit">Book this day</button>
                    </form>
                {% else %}
                    <button class="btn btn-disabled" disabled>Full</button>
                {% endif %}
                </div>
            </div>
        {% endfor %}

        <p><a href="{{ url_for('admin') }}">Admin view</a></p>
    </body>
    </html>
    """
    return render_template_string(template, days=list(bookings_per_day.items()))


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
        flash(("error", "Invalid date format."))
        return redirect(url_for("index"))

    # Ensure it's a Saturday and in the future (or today)
    if visit_date.weekday() != 5:
        flash(("error", "Only Saturdays can be booked."))
        return redirect(url_for("index"))
    if visit_date < date.today():
        flash(("error", "You cannot book a past date."))
        return redirect(url_for("index"))

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) as cnt FROM bookings WHERE visit_date = ?", (visit_date.isoformat(),))
    booked = c.fetchone()["cnt"]

    if booked >= 2:
        conn.close()
        flash(("error", "This Saturday is already full."))
        return redirect(url_for("index"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()

        if not name or not email:
            flash(("error", "Please fill in your name and email."))
            conn.close()
            return redirect(url_for("book") + f"?date={visit_date_str}")

        # Save booking
        c.execute(
            "INSERT INTO bookings (visit_date, name, email, created_at) VALUES (?, ?, ?, ?)",
            (visit_date.isoformat(), name, email, datetime.utcnow().isoformat())
        )
        conn.commit()
        conn.close()
        flash(("success", "Your visit has been booked!"))
        return redirect(url_for("index"))

    # GET: show form
    template = """
    <!doctype html>
    <html>
    <head>
        <title>Book Visit for {{ visit_date.strftime("%d %B %Y") }}</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: sans-serif; max-width: 600px; margin: 20px auto; padding: 0 10px; }
            label { display: block; margin-top: 10px; }
            input { width: 100%; padding: 6px; margin-top: 4px; box-sizing: border-box; }
            .btn { margin-top: 15px; padding: 8px 12px; border-radius: 4px; border: none; background: #007bff; color: white; cursor: pointer; }
            .btn-back { margin-top: 10px; display: inline-block; }
        </style>
    </head>
    <body>
        <h1>Book visit for {{ visit_date.strftime("%A %d %B %Y") }}</h1>
        <form method="post">
            <input type="hidden" name="visit_date" value="{{ visit_date.isoformat() }}">
            <label>Your name
                <input type="text" name="name" required>
            </label>
            <label>Your email
                <input type="email" name="email" required>
            </label>
            <button class="btn" type="submit">Confirm booking</button>
        </form>
        <p><a class="btn-back" href="{{ url_for('index') }}">← Back</a></p>
    </body>
    </html>
    """
    conn.close()
    return render_template_string(template, visit_date=visit_date)


@app.route("/admin")
def admin():
    """Very simple overview of all bookings, no auth for demo."""
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM bookings ORDER BY visit_date, created_at")
    rows = c.fetchall()
    conn.close()

    template = """
    <!doctype html>
    <html>
    <head>
        <title>Admin - Bookings</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: sans-serif; max-width: 800px; margin: 20px auto; padding: 0 10px; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #ccc; padding: 6px 8px; }
            th { background: #eee; }
        </style>
    </head>
    <body>
        <h1>All bookings</h1>
        <table>
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
        <p><a href="{{ url_for('index') }}">← Back to booking</a></p>
    </body>
    </html>
    """
    return render_template_string(template, rows=rows)


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_db()
    else:
        # ensure table exists
        init_db()
    app.run(debug=True)

