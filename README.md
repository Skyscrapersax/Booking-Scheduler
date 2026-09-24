# Booking Scheduler

A private operator desk for one shared calendar: persistent bookings, atomic
overlap protection, cancellation history and calendar-file downloads.

Bookings can now be edited/rescheduled in place with conflict checks, stale-edit
protection, change history and stable calendar IDs/revisions. Search covers old
and cancelled bookings. Sign-in throttles persist across workers and restarts.

For **Vercel**, follow [deployment and migration setup](DEPLOYMENT.md): external
PostgreSQL, explicit schema initialization, secure settings and staged CDN assets.
SQLite remains the local option; the hosted entrypoint refuses ephemeral storage.

Start with [pilot setup, verification and release limits](README.pilot.md).

The app requires credentials and uses SQLite locally or PostgreSQL on Vercel. No public self-booking, messages,
payments or external calendar synchronization are enabled.
