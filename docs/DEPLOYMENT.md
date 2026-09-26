# Deployment, backups and exports

## Production outline
1. Use a Linux VM or PaaS with Python 3.11 or newer. Install the packages with `pip install Flask psycopg[binary] gunicorn`.
2. Create a PostgreSQL 14+ database and user. Set `DATABASE_URL=postgresql://…`.
3. Copy `.env.example` to `.env` and set `APP_ENV=production` and a long random `SECRET_KEY`. Point `UPLOAD_DIR` at a private, backed-up volume.
4. Run `flask --app wsgi init-db`, then `flask --app wsgi seed-base`. **Never** run `seed-demo` in production (it refuses when `APP_ENV=production`).
5. Run `flask --app wsgi create-superadmin` and sign in. Then fill in the branch details, hours, rooms, dentist schedules and website content, and create the other users.
6. Serve the app with `gunicorn -w 3 -b 127.0.0.1:8000 wsgi:app` behind nginx or Caddy with HTTPS. Set `X-Forwarded-For` so the public-form rate limit sees the real client IP. With more than one worker or server, the in-memory rate limit counts each worker separately; move it to Redis or the proxy if that matters.
7. Schedule a daily job for `flask --app wsgi generate-reminders`. It queues reminders only.

**About PostgreSQL:** the SQL is written to run on both databases (placeholders are rewritten and `AUTOINCREMENT` becomes `BIGSERIAL`). However, the test suite ran on SQLite only, because no PostgreSQL driver could be installed in the build environment. Before going live, run the test suite against a Postgres database: set `DATABASE_URL` and run `python -m unittest`. Appointment conflict checks run inside a SERIALIZABLE transaction on Postgres, which does the same job as SQLite's write lock. For extra safety you can add an exclusion constraint such as `EXCLUDE USING gist (dentist_id WITH =, tsrange(start_at::timestamp, end_at::timestamp) WITH &&) WHERE (status IN ('requested','confirmed','checked_in'))` with the `btree_gist` extension.

## Backups
- **Database:** take a nightly `pg_dump -Fc` (or, for SQLite, `sqlite3 instance/dental_haven.db ".backup backup.db"`). Encrypt it with age or GPG, copy it off-site, keep 30 daily and 12 monthly copies, and test a restore every quarter.
- **Uploads:** back up `UPLOAD_DIR` (patient documents) and `app/static/uploads/` (the public gallery) on the same schedule.
- **Secrets:** keep `.env` in a password manager, not with the backups.

## Exports
- Reports: CSV exports of sales, services, payments, outstanding balances and appointments. Exports require `reports.export` and are logged.
- Payroll: a CSV for each period, labelled DRAFT or APPROVED SUMMARY.
- Full data export: use `pg_dump`. For one patient's data-subject request, print their profile, clinical tab and documents from the patient page.
