#!/usr/bin/env bash
# Installs the short commands (dental-haven-update, dental-haven-https, dental-haven-backup).
# They call the scripts through bash, so they keep working even if the files lose their
# "executable" mark (which happens when the code passes through Windows / GitHub Desktop).
set -euo pipefail
HERE="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
install_wrapper() {  # name, script
  rm -f "/usr/local/sbin/$1"   # remove first: writing through an old symlink would overwrite the script itself
  printf '#!/bin/sh\nexec bash "%s" "$@"\n' "$HERE/$2" > "/usr/local/sbin/$1"
  chmod 755 "/usr/local/sbin/$1"
}
install_wrapper dental-haven-update update.sh
install_wrapper dental-haven-https enable-https.sh
# The backup script is copied (not linked) because the nightly job runs it; keep its folder settings.
if [ -f /usr/local/sbin/dental-haven-backup ]; then
  data="$(grep '^DATA_DIR=' /usr/local/sbin/dental-haven-backup)"; dest="$(grep '^BACKUP_DIR=' /usr/local/sbin/dental-haven-backup)"
  rm -f /usr/local/sbin/dental-haven-backup
  sed -e "s|^DATA_DIR=.*|$data|" -e "s|^BACKUP_DIR=.*|$dest|" "$HERE/backup.sh" > /usr/local/sbin/dental-haven-backup
  chmod 755 /usr/local/sbin/dental-haven-backup
fi
