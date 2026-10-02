#!/usr/bin/env bash
# Nightly database backup (installed as /usr/local/sbin/dental-haven-backup; runs 11:30 PM).
# Makes a safe copy of the live database while the system is running and keeps the last 14.
# Uploaded files are covered by the DigitalOcean Droplet backups and by
# Administration -> System settings -> Download full backup.
set -euo pipefail
DATA_DIR="/var/lib/dental-haven"
BACKUP_DIR="/var/backups/dental-haven"
KEEP_DAYS=14
mkdir -p "$BACKUP_DIR"; chmod 700 "$BACKUP_DIR"
stamp="$(date +%Y%m%d-%H%M)"
out="$BACKUP_DIR/db-$stamp.sqlite"
sqlite3 "$DATA_DIR/dental_haven.db" ".backup '$out'"
[ "$(sqlite3 "$out" 'PRAGMA integrity_check;')" = "ok" ] || { echo "Backup failed its check: $out" >&2; exit 1; }
gzip -f "$out"; chmod 600 "$out.gz"
find "$BACKUP_DIR" -name 'db-*.sqlite.gz' -mtime +"$KEEP_DAYS" -delete
echo "Saved $out.gz"
