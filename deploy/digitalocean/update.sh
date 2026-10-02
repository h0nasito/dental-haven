#!/usr/bin/env bash
# Get the newest version from GitHub and restart (run as root:  dental-haven-update).
# Makes a database backup first. Database changes (migrations) run automatically on restart.
set -euo pipefail
APP_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../.." && pwd)"
[ "$(id -u)" -eq 0 ] || { echo "Run as root." >&2; exit 1; }
echo "==> Backing up the database first"
/usr/local/sbin/dental-haven-backup
echo "==> Getting the newest version"
git -C "$APP_DIR" pull --ff-only
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt" -q
echo "==> Restarting"
systemctl restart dental-haven
for _ in $(seq 1 30); do
  if curl -fsS -o /dev/null http://127.0.0.1:8000/; then
    echo "Updated to: $(git -C "$APP_DIR" log -1 --format='%h %s')"; exit 0
  fi
  sleep 2
done
echo "The system didn't come back. See:  journalctl -u dental-haven -n 50 --no-pager" >&2
exit 1
