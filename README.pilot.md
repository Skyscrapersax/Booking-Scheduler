# Booking Scheduler — private operator pilot

One shared calendar for a small appointment or studio desk. This replaces the
repository's Flask welcome screen with persistent bookings, conflict prevention,
cancellation history and downloadable calendar files. Related Maroon Room UI is
tracked separately; its booking button has not been wired to this service.

**Current Vercel release:** see [DEPLOYMENT.md](DEPLOYMENT.md). Maroon Room has its
own request/approval workflow and independent calendar. Both apps support durable
PostgreSQL hosting; this guide's file paths/Waitress examples describe local use.

## Run locally

Python 3.11+ and an IANA timezone database are required.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest -v
export BOOKING_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
# Choose a private password with at least 16 characters:
read -s BOOKING_PASSWORD
export BOOKING_PASSWORD
export BOOKING_COOKIE_SECURE=0  # loopback HTTP only
.venv/bin/waitress-serve --listen=127.0.0.1:8794 --call app:create_app
```

Open <http://127.0.0.1:8794/>. Set `BOOKING_TIMEZONE` to an IANA zone if needed;
default is `America/New_York`. Dates are shown in that zone, storage and exports
use UTC. Repeated or skipped DST wall times are rejected instead of guessed.
Bookings must start in the future, within one year. Durations mean elapsed time.

`BOOKING_DATABASE` selects the SQLite file; default `instance/bookings.sqlite3`.
Keep the same DB path and secret across restarts. Storage is excluded from Git.
Tests use temporary databases; no real appointments or contacts are needed.
At startup, the app enforces mode `0600` on the main database file. Keep its parent
directory private, including custom paths; existing directory and SQLite sidecar
permissions are not changed by the app.

## Pilot boundary

One trusted operator team, one calendar, one persistent host. SQLite serializes
overlap checks with inserts, preventing double booking across concurrent requests.
Form IDs prevent duplicate submissions. Cancelling frees a slot but retains history;
use **Edit or reschedule** to move an existing booking while preserving its ID and
previous details. Concurrent/stale edits cannot overwrite a newer revision.
Search all bookings and cancellations through **History**. Calendar export is a manual `.ics`
download, not an invitation or two-way sync. No emails, payments or other external
actions occur. Calendar applications may handle repeated imports differently;
actual Apple/Google/Outlook import behavior still needs pilot validation.

Run on loopback or behind a private authenticated network. Before remote use,
set a stable private secret/password, `BOOKING_HOST` to the exact host, keep secure
cookies enabled, and terminate HTTPS at a trusted reverse proxy. Sign-in is limited
to ten attempts per address per 15 minutes in the shared database. Forwarded client
addresses are trusted only in Vercel mode. There are no per-user accounts,
password recovery or role separation. Do not place SQLite on a network filesystem;
Vercel instances use one shared PostgreSQL database instead.

Use SQLite's backup API for live backups (copying only the main file while WAL
is active can omit recent writes). Example using an existing DB path:

```sh
umask 077
python3 -c 'import sqlite3; source=sqlite3.connect("instance/bookings.sqlite3"); target=sqlite3.connect("/private/backup/bookings.sqlite3"); source.backup(target); target.close(); source.close()'
```

Use a private backup directory and a new target file; `umask` does not tighten an
existing file's permissions. Protect backups like client data. Restore a backup into a separate pilot instance
and verify bookings before adopting it. Automated backups, restore drills and
production hosting are not configured by this change.

The pinned [Flask release](https://pypi.org/project/Flask/3.1.3/) runs through
[Waitress](https://docs.pylonsproject.org/projects/waitress/en/stable/).
Flask's development server is not used for this rehearsal; see
[Flask deployment guidance](https://flask.palletsprojects.com/en/stable/deploying/).

## Delivery state, 14 September 2026

**70/100 for a private single-calendar pilot**, judgment rather than customer
validation: workflow 20/25, safety 14/20, UX 12/15, operations 8/15,
verification 13/15, commercial evidence 3/10. No prior numeric score was verified;
the original implementation only rendered the Codespaces welcome screen.

Nine standard-library tests cover existing database permissions, persistence/restart, replay, cancellation and
rebooking, atomic concurrency, adjacent versus overlapping slots, auth/CSRF/host
checks, invalid input, DST, HTML escaping and ICS injection/UTF-8 line folding.
Dependency resolution passes `pip check`; no vulnerability-audit result is claimed.

Local branch: `codex/booking-pilot-20260914`. GitHub API reports `push: false` for
`kohlkat/Booking-Scheduler`; upstream publication remains blocked on collaborator
access. No fork, external deployment, domain change or account change was made.
