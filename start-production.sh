#!/usr/bin/env bash
# Starts the LIVE clinic site (used by render.live.yaml). Data lives on the persistent disk (DATA_DIR).
# Never loads demo data. Safe to run on every start: migrations and base setup only add what's missing.
set -euo pipefail
: "${DATA_DIR:?Set DATA_DIR to the persistent disk path (e.g. /var/data).}"
if [ ! -d "$DATA_DIR" ]; then
  echo "DATA_DIR ($DATA_DIR) doesn't exist. Attach a persistent disk mounted there." >&2
  exit 1
fi
if [ "${APP_ENV:-}" != "production" ]; then
  echo "APP_ENV must be 'production' for the live site." >&2
  exit 1
fi
flask --app wsgi init-db
flask --app wsgi seed-base
flask --app wsgi ensure-admin
exec gunicorn wsgi:app --bind "0.0.0.0:${PORT:-8000}" --workers 2 --threads 4 --timeout 120
