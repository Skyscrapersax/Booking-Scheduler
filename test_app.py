from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path
import re
import secrets
import sqlite3
import tempfile
import unittest
from zoneinfo import ZoneInfo

from app import create_app, local_timestamp


class BookingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = dict(TESTING=True, SECRET_KEY="test-session-secret-" * 3, ADMIN_PASSWORD="test-password-only-2026",
                           DATABASE=str(Path(self.temp.name) / "bookings.sqlite3"), SESSION_COOKIE_SECURE=False)
        self.app = create_app(self.config)
        self.client = self.login(self.app.test_client())
        self.start = (datetime.now(ZoneInfo("America/New_York")) + timedelta(days=14)).replace(hour=12, minute=0).strftime("%Y-%m-%dT%H:%M")

    def login(self, client):
        client.get("/login")
        with client.session_transaction() as session:
            csrf = session["csrf"]
        self.assertEqual(client.post("/login", data={"password": self.config["ADMIN_PASSWORD"], "csrf": csrf}).status_code, 303)
        return client

    def form(self, http_client=None, **changes):
        http_client = http_client or self.client
        with http_client.session_transaction() as session:
            csrf = session["csrf"]
        return dict(title="Recording", client="Example Artist", contact="example@example.invalid", notes="", start=self.start,
                    minutes="60", day=self.start[:10], request_id=secrets.token_urlsafe(24), csrf=csrf) | changes

    def rows(self):
        with closing(sqlite3.connect(self.config["DATABASE"])) as conn:
            return conn.execute("SELECT id,cancelled FROM bookings ORDER BY id").fetchall()

    def test_save_persist_replay_cancel_rebook_and_calendar(self):
        form = self.form()
        saved = self.client.post("/bookings", data=form)
        self.assertEqual(saved.status_code, 303)
        self.assertEqual(self.client.post("/bookings", data=form).status_code, 303)
        self.assertEqual(len(self.rows()), 1)
        restarted = self.login(create_app(self.config).test_client())
        self.assertIn(b"Example Artist", restarted.get(saved.location).data)
        calendar = self.client.get("/bookings/1.ics")
        self.assertEqual(calendar.status_code, 200)
        self.assertIn(b"STATUS:CONFIRMED", calendar.data)
        self.assertRegex(calendar.data, rb"DTSTART:\d{8}T\d{6}Z")
        self.assertEqual(self.client.post("/bookings/1/cancel", data={"csrf": form["csrf"]}).status_code, 303)
        self.assertIsNotNone(self.rows()[0][1])
        self.assertIn(b"STATUS:CANCELLED", self.client.get("/bookings/1.ics").data)
        self.assertEqual(self.client.post("/bookings", data=self.form()).status_code, 303)
        self.assertEqual(len(self.rows()), 2)

    def test_overlap_is_atomic_under_concurrent_requests(self):
        def attempt(_):
            client = self.login(self.app.test_client())
            return client.post("/bookings", data=self.form(client)).status_code
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(attempt, range(4)))
        self.assertEqual(sorted(results), [303, 409, 409, 409])
        self.assertEqual(len(self.rows()), 1)

    def test_adjacent_slots_allowed_but_partial_overlap_rejected(self):
        self.assertEqual(self.client.post("/bookings", data=self.form()).status_code, 303)
        self.assertEqual(self.client.post("/bookings", data=self.form(start=self.start[:11]+"12:30")).status_code, 409)
        self.assertEqual(self.client.post("/bookings", data=self.form(start=self.start[:11]+"13:00")).status_code, 303)

    def test_private_routes_csrf_and_host_rejection(self):
        anonymous = self.app.test_client()
        for path in ["/", "/bookings/1.ics"]:
            self.assertEqual(anonymous.get(path).status_code, 302)
        for csrf in ["", "bad", "悪い"]:
            self.assertEqual(self.client.post("/bookings", data=self.form(csrf=csrf)).status_code, 400)
        self.assertEqual(self.client.get("/", headers={"Host": "attacker.invalid"}).status_code, 400)
        self.assertEqual(self.client.get("/bookings/99999999999999999999999.ics").status_code, 404)
        self.assertEqual(self.client.post("/logout", data={"csrf": self.form()["csrf"]}).status_code, 303)
        self.assertEqual(self.client.get("/").status_code, 302)

    def test_bad_input_keeps_form_and_writes_nothing(self):
        for changes in [dict(title=""), dict(minutes="1"), dict(start="2020-01-01T12:00"), dict(start="bad"),
                        dict(request_id="x\nBEGIN:VEVENT"), dict(client="x"*121)]:
            with self.subTest(changes=changes):
                response = self.client.post("/bookings", data=self.form(**changes))
                self.assertEqual(response.status_code, 422)
                self.assertIn(b"Recording" if "title" not in changes else b"Example Artist", response.data)
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.client.get("/?day=9999-12-31").status_code, 400)

    def test_dst_rejects_both_skipped_and_ambiguous_wall_times(self):
        zone = ZoneInfo("America/New_York")
        for wall_time in ["2026-03-08T02:30", "2026-11-01T01:30"]:
            with self.assertRaisesRegex(ValueError, "daylight saving"):
                local_timestamp(wall_time, zone)
        self.assertIsInstance(local_timestamp("2026-11-01T03:30", zone), int)

    def test_html_and_calendar_injection_and_utf8_line_folding(self):
        form = self.form(title="<script>alert(1)</script>", notes="🎵"*100 + "\nBEGIN:VEVENT\nSUMMARY:injected,unsafe;value")
        response = self.client.post("/bookings", data=form, follow_redirects=True)
        self.assertIn(b"&lt;script&gt;", response.data)
        self.assertNotIn(b"<script>", response.data)
        data = self.client.get("/bookings/1.ics").data
        self.assertEqual(data.count(b"\r\nBEGIN:VEVENT\r\n"), 1)
        self.assertTrue(all(len(line) <= 75 for line in data.split(b"\r\n")))
        data.decode("utf-8")
        self.assertIn(b"\\nBEGIN:VEVENT", data.replace(b"\r\n ", b""))

    def test_missing_credentials_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "BOOKING_SECRET"):
            create_app(self.config | {"SECRET_KEY": "", "ADMIN_PASSWORD": ""})


if __name__ == "__main__":
    unittest.main()
