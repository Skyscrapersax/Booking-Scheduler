"""Private single-calendar booking desk. No external messages or payments."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import hmac
import os
from pathlib import Path
import re
import secrets
import sqlite3
from zoneinfo import ZoneInfo

from flask import Flask, Response, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


def local_timestamp(value, zone):
    try:
        naive = datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError:
        raise ValueError("Enter a valid date and time.") from None
    stamps = {int(naive.replace(tzinfo=zone, fold=fold).timestamp()) for fold in (0, 1)
              if datetime.fromtimestamp(naive.replace(tzinfo=zone, fold=fold).timestamp(), zone).replace(tzinfo=None) == naive}
    if len(stamps) != 1:
        raise ValueError("That local time is skipped or repeated by daylight saving. Choose an unambiguous time.")
    return stamps.pop()


def calendar_text(value):
    return value.replace("\\", "\\\\").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def fold_calendar(lines):
    folded = []
    for line in lines:
        data = line.encode("utf-8")
        while len(data) > 75:
            cut = 75
            while data[cut] & 0xC0 == 0x80:
                cut -= 1
            folded.append(data[:cut].decode("utf-8"))
            data = b" " + data[cut:]
        folded.append(data.decode("utf-8"))
    return "\r\n".join(folded) + "\r\n"


def create_app(config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("BOOKING_SECRET", ""), ADMIN_PASSWORD=os.environ.get("BOOKING_PASSWORD", ""),
        DATABASE=os.environ.get("BOOKING_DATABASE", str(Path(app.instance_path) / "bookings.sqlite3")),
        TIMEZONE=os.environ.get("BOOKING_TIMEZONE", "America/New_York"),
        SESSION_COOKIE_NAME="booking_desk_session", SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Strict", SESSION_COOKIE_SECURE=os.environ.get("BOOKING_COOKIE_SECURE") != "0",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8), MAX_CONTENT_LENGTH=16384,
        TRUSTED_HOSTS=["localhost", "127.0.0.1"] + ([os.environ["BOOKING_HOST"]] if os.environ.get("BOOKING_HOST") else []),
    )
    app.config.update(config or {})
    if len(app.config["SECRET_KEY"]) < 32 or len(app.config["ADMIN_PASSWORD"]) < 16:
        raise ValueError("Set BOOKING_SECRET (32+ characters) and BOOKING_PASSWORD (16+ characters).")
    password_hash = generate_password_hash(app.config.pop("ADMIN_PASSWORD"))
    zone = ZoneInfo(app.config["TIMEZONE"])
    database = Path(app.config["DATABASE"])
    database.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    database.touch(mode=0o600, exist_ok=True)
    database.chmod(0o600)

    def db():
        conn = sqlite3.connect(database, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    with closing(db()) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY, title TEXT NOT NULL, client TEXT NOT NULL,
            contact TEXT NOT NULL, notes TEXT NOT NULL, starts INTEGER NOT NULL,
            ends INTEGER NOT NULL CHECK(ends > starts), created INTEGER NOT NULL,
            cancelled INTEGER, request_id TEXT NOT NULL UNIQUE)""")
        conn.execute("CREATE INDEX IF NOT EXISTS booking_times ON bookings(starts, ends) WHERE cancelled IS NULL")
        conn.commit()

    @app.before_request
    def protect():
        if request.routing_exception is not None:
            return  # Let Flask reject invalid hosts/routes before building redirects.
        session.setdefault("csrf", secrets.token_urlsafe(32))
        if request.method == "POST" and not hmac.compare_digest(session["csrf"].encode(), request.form.get("csrf", "").encode()):
            abort(400, "Form expired. Reload the page and try again.")
        if request.endpoint not in {"login", "static"} and not session.get("signed_in"):
            return redirect(url_for("login"))

    @app.after_request
    def headers(response):
        response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "same-origin", "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"})
        return response

    @app.template_filter("localtime")
    def localtime(stamp):
        return datetime.fromtimestamp(stamp, zone).strftime("%a %d %b · %H:%M %Z")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            if check_password_hash(password_hash, request.form.get("password", "")):
                session.clear()
                session.update(signed_in=True, csrf=secrets.token_urlsafe(32))
                session.permanent = True
                return redirect(url_for("index"), code=303)
            return render_template("index.html", login=True, error="Password not recognized."), 401
        return render_template("index.html", login=True)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"), code=303)

    def desk(error=None, status=200):
        day = request.args.get("day") or request.form.get("day") or datetime.now(zone).date().isoformat()
        try:
            date = datetime.strptime(day, "%Y-%m-%d").date()
            if not 2000 <= date.year <= 2100:
                raise ValueError()
        except ValueError:
            abort(400, "Invalid calendar date.")
        start = int(datetime.combine(date, datetime.min.time(), zone).timestamp())
        end = int(datetime.combine(date + timedelta(days=1), datetime.min.time(), zone).timestamp())
        with closing(db()) as conn:
            bookings = conn.execute("SELECT * FROM bookings WHERE starts < ? AND ends > ? ORDER BY starts, id", (end, start)).fetchall()
        now = datetime.now(zone)
        suggested = (now + timedelta(minutes=15 - now.minute % 15)).strftime("%Y-%m-%dT%H:%M") if date == now.date() else date.isoformat() + "T10:00"
        return render_template("index.html", day=date.isoformat(), bookings=bookings, zone=zone.key,
            previous=(date-timedelta(days=1)).isoformat(), following=(date+timedelta(days=1)).isoformat(),
            error=error, values=request.form, suggested=suggested, request_id=request.form.get("request_id") or secrets.token_urlsafe(24)), status

    @app.get("/")
    def index():
        return desk()

    @app.post("/bookings")
    def book():
        values = {key: request.form.get(key, "").strip() for key in ("title", "client", "contact", "notes", "request_id")}
        try:
            for key, limit in [("title", 120), ("client", 120), ("contact", 200), ("notes", 2000)]:
                if len(values[key]) > limit or any(ord(c) < 32 and c not in "\n\t" for c in values[key]):
                    raise ValueError(f"Check {key}: text too long or contains unsupported characters.")
            if not values["title"] or not values["client"]:
                raise ValueError("Session title and client are required.")
            if not re.fullmatch(r"[A-Za-z0-9_-]{20,100}", values["request_id"]):
                raise ValueError("Form identifier invalid. Reload and try again.")
            starts = local_timestamp(request.form.get("start", ""), zone)
            minutes = int(request.form.get("minutes", "0"))
            if minutes not in (15, 30, 45, 60, 90, 120, 180, 240, 480):
                raise ValueError("Choose a supported duration.")
            now = int(datetime.now(timezone.utc).timestamp())
            if not now < starts <= now + 366 * 86400:
                raise ValueError("Choose a future time within the next year.")
            ends = starts + minutes * 60
        except ValueError as exc:
            return desk(str(exc), 422)
        with closing(db()) as conn:
            # One calendar, one SQLite writer. Check and insert share a transaction.
            conn.execute("BEGIN IMMEDIATE")
            duplicate = conn.execute("SELECT id FROM bookings WHERE request_id=?", (values["request_id"],)).fetchone()
            if duplicate:
                flash("This form was already saved; no duplicate booking created.")
            elif conn.execute("SELECT id FROM bookings WHERE cancelled IS NULL AND starts < ? AND ends > ?", (ends, starts)).fetchone():
                return desk("That time overlaps an existing booking. Choose another time or cancel the existing booking first.", 409)
            else:
                conn.execute("INSERT INTO bookings(title,client,contact,notes,starts,ends,created,request_id) VALUES(?,?,?,?,?,?,?,?)",
                    (values["title"], values["client"], values["contact"], values["notes"], starts, ends, now, values["request_id"]))
                conn.commit()
                flash("Booking saved. No invitation or message has been sent.")
        return redirect(url_for("index", day=datetime.fromtimestamp(starts, zone).date().isoformat()), code=303)

    @app.post("/bookings/<int:booking_id>/cancel")
    def cancel(booking_id):
        if booking_id > 2**63 - 1:
            abort(404)
        with closing(db()) as conn:
            row = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
            if row is None:
                abort(404)
            conn.execute("UPDATE bookings SET cancelled=? WHERE id=? AND cancelled IS NULL",
                (int(datetime.now(timezone.utc).timestamp()), booking_id))
            conn.commit()
        flash("Booking cancelled. History retained; no message sent.")
        return redirect(url_for("index", day=datetime.fromtimestamp(row["starts"], zone).date().isoformat()), code=303)

    @app.get("/bookings/<int:booking_id>.ics")
    def calendar(booking_id):
        if booking_id > 2**63 - 1:
            abort(404)
        with closing(db()) as conn:
            row = conn.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
        if row is None:
            abort(404)
        utc = lambda stamp: datetime.fromtimestamp(stamp, timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Booking Scheduler//Private Pilot//EN", "BEGIN:VEVENT",
            f"UID:{row['request_id']}@booking-scheduler.local", f"DTSTAMP:{utc(row['cancelled'] or row['created'])}",
            f"DTSTART:{utc(row['starts'])}", f"DTEND:{utc(row['ends'])}", "SUMMARY:" + calendar_text(row["title"]),
            "DESCRIPTION:" + calendar_text(f"Client: {row['client']}\n{row['contact']}\n{row['notes']}"),
            "STATUS:" + ("CANCELLED" if row["cancelled"] else "CONFIRMED"),
            "SEQUENCE:" + ("1" if row["cancelled"] else "0"), "END:VEVENT", "END:VCALENDAR"]
        return Response(fold_calendar(lines), mimetype="text/calendar",
            headers={"Content-Disposition": f'attachment; filename="booking-{booking_id}.ics"'})

    return app
