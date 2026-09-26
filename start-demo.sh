#!/usr/bin/env bash
# Starts the online DEMO: fresh database with synthetic data on every start, then the web server.
# Used by render.yaml. Do not use for the real clinic (see docs/DEPLOYMENT.md).
set -euo pipefail
if [ -z "${DEMO_PASSWORD:-}" ]; then
  echo "Set DEMO_PASSWORD (at least 10 characters) in the hosting dashboard." >&2
  exit 1
fi
mkdir -p instance
rm -f instance/dental_haven.db instance/dental_haven.db-wal instance/dental_haven.db-shm
flask --app wsgi init-db
flask --app wsgi seed-demo --password "$DEMO_PASSWORD" > /dev/null
echo "Demo data loaded."
exec gunicorn wsgi:app --bind "0.0.0.0:${PORT:-8000}" --workers 1 --threads 4 --timeout 300
