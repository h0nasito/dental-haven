#!/usr/bin/env bash
# One-time setup of the LIVE Dental Haven system on a fresh DigitalOcean Droplet (Ubuntu 24.04).
# Run as root from the cloned code folder:   bash /opt/dental-haven/deploy/digitalocean/setup.sh
# Safe to run again: it keeps the existing database, uploads and secret key.
# Full guide: docs/DEPLOY_DIGITALOCEAN.md
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_USER="dentalhaven"
DATA_DIR="/var/lib/dental-haven"
ENV_DIR="/etc/dental-haven"
ENV_FILE="$ENV_DIR/env"
BACKUP_DIR="/var/backups/dental-haven"
HERE="$APP_DIR/deploy/digitalocean"

say()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\n\033[1;33m!!  %s\033[0m\n' "$*"; }
die()  { printf '\n\033[1;31mXX  %s\033[0m\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "Run this as root (in the DigitalOcean Console you already are root)."
[ -f "$APP_DIR/wsgi.py" ] || die "Can't find the code in $APP_DIR."
. /etc/os-release
[ "${ID:-}" = "ubuntu" ] || warn "This script was written for Ubuntu 24.04; you are on ${PRETTY_NAME:-unknown}."

# ---------------------------------------------------------------- questions
say "A few questions (press Enter to accept the value in [brackets])"
read -rp "Domain name for the system [dentalhaven.net]: " DOMAIN
DOMAIN="${DOMAIN:-dentalhaven.net}"
DOMAIN="${DOMAIN#https://}"; DOMAIN="${DOMAIN#http://}"; DOMAIN="${DOMAIN%%/*}"; DOMAIN="${DOMAIN#www.}"
read -rp "Also answer on www.$DOMAIN? (y/n) [y]: " USE_WWW
USE_WWW="${USE_WWW:-y}"

NEED_ADMIN=1
if [ -f "$DATA_DIR/dental_haven.db" ]; then
  NEED_ADMIN=0
  echo "An existing database was found in $DATA_DIR. It will be kept; no new admin is created."
fi
if [ "$NEED_ADMIN" -eq 1 ]; then
  read -rp "Clinic owner's email (first super admin login): " ADMIN_EMAIL
  [ -n "$ADMIN_EMAIL" ] || die "An email is required."
  read -rp "Clinic owner's name [Clinic administrator]: " ADMIN_NAME
  ADMIN_NAME="${ADMIN_NAME:-Clinic administrator}"
  while true; do
    read -rsp "Temporary password (10+ characters, upper and lower case, a number; nothing shows as you type): " ADMIN_PW; echo
    read -rsp "Type it again: " ADMIN_PW2; echo
    if [ "$ADMIN_PW" != "$ADMIN_PW2" ]; then echo "They didn't match. Try again."; continue; fi
    if [ "${#ADMIN_PW}" -lt 10 ] || ! [[ "$ADMIN_PW" =~ [a-z] ]] || ! [[ "$ADMIN_PW" =~ [A-Z] ]] || ! [[ "$ADMIN_PW" =~ [0-9] ]]; then
      echo "Too weak: use 10+ characters with upper- and lower-case letters and a number."; continue
    fi
    break
  done
  unset ADMIN_PW2
fi
read -rp "Email for HTTPS certificate notices [${ADMIN_EMAIL:-}]: " LE_EMAIL
LE_EMAIL="${LE_EMAIL:-${ADMIN_EMAIL:-}}"

# ---------------------------------------------------------------- system packages
say "Installing system updates and packages (this takes a few minutes)"
export DEBIAN_FRONTEND=noninteractive
timedatectl set-timezone Asia/Manila || true
apt-get update -y
apt-get upgrade -y
apt-get install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx \
  sqlite3 ufw fail2ban unattended-upgrades git curl
dpkg-reconfigure -f noninteractive unattended-upgrades || true

# Small swap file so installs and busy hours never run out of memory.
if ! swapon --show | grep -q .; then
  say "Adding a 1 GB swap file"
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# ---------------------------------------------------------------- firewall
say "Turning on the firewall (only SSH, HTTP and HTTPS are open)"
ufw allow OpenSSH >/dev/null
ufw allow 'Nginx Full' >/dev/null
ufw --force enable
systemctl enable --now fail2ban

# ---------------------------------------------------------------- app user, folders, Python
say "Creating the app user and folders"
id "$APP_USER" >/dev/null 2>&1 || useradd --system --home "$DATA_DIR" --shell /usr/sbin/nologin "$APP_USER"
install -d -m 700 -o "$APP_USER" -g "$APP_USER" "$DATA_DIR"
install -d -m 750 -o root -g "$APP_USER" "$ENV_DIR"
install -d -m 700 -o root -g root "$BACKUP_DIR"
install -d -m 755 -o "$APP_USER" -g "$APP_USER" "$APP_DIR/instance"

say "Installing the Python packages"
[ -d "$APP_DIR/.venv" ] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip -q
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt" -q

# ---------------------------------------------------------------- settings file
if [ ! -f "$ENV_FILE" ]; then
  say "Writing the settings file $ENV_FILE (with a new random secret key)"
  SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  sed -e "s|__SECRET_KEY__|$SECRET|" -e "s|__DOMAIN__|$DOMAIN|" -e "s|__DATA_DIR__|$DATA_DIR|" \
    "$HERE/env.template" > "$ENV_FILE"
  unset SECRET
else
  say "Keeping the existing settings file $ENV_FILE"
  sed -i "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=https://$DOMAIN|" "$ENV_FILE"
fi
chown root:"$APP_USER" "$ENV_FILE"; chmod 640 "$ENV_FILE"

# ---------------------------------------------------------------- database + first admin
say "Preparing the database"
run_flask() {  # run a flask command as the app user with the live settings
  sudo -u "$APP_USER" env -C "$APP_DIR" bash -c 'set -a; . "$0"; set +a; shift; exec "$@"' \
    "$ENV_FILE" _ "$APP_DIR/.venv/bin/flask" --app wsgi "$@"
}
run_flask init-db
run_flask seed-base
if [ "$NEED_ADMIN" -eq 1 ]; then
  # The password is passed to this one command only. It is never written to disk.
  sudo -u "$APP_USER" env -C "$APP_DIR" INITIAL_ADMIN_EMAIL="$ADMIN_EMAIL" INITIAL_ADMIN_NAME="$ADMIN_NAME" \
    INITIAL_ADMIN_PASSWORD="$ADMIN_PW" bash -c 'set -a; . "$0"; set +a; exec "$1" --app wsgi ensure-admin' \
    "$ENV_FILE" "$APP_DIR/.venv/bin/flask"
  unset ADMIN_PW
fi

# ---------------------------------------------------------------- service
say "Installing the background service (starts automatically after a reboot)"
sed -e "s|__APP_DIR__|$APP_DIR|g" -e "s|__APP_USER__|$APP_USER|g" -e "s|__ENV_FILE__|$ENV_FILE|g" \
    -e "s|__DATA_DIR__|$DATA_DIR|g" "$HERE/dental-haven.service" > /etc/systemd/system/dental-haven.service
systemctl daemon-reload
systemctl enable dental-haven >/dev/null
systemctl restart dental-haven

# ---------------------------------------------------------------- nginx
say "Setting up the web server for $DOMAIN"
NAMES="$DOMAIN"; [ "$USE_WWW" = "y" ] && NAMES="$DOMAIN www.$DOMAIN"
if [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ] && [ -f /etc/nginx/sites-available/dental-haven ]; then
  echo "HTTPS is already set up; keeping the existing web server settings."
else
  sed -e "s|__SERVER_NAMES__|$NAMES|" "$HERE/nginx.conf" > /etc/nginx/sites-available/dental-haven
  ln -sf /etc/nginx/sites-available/dental-haven /etc/nginx/sites-enabled/dental-haven
  rm -f /etc/nginx/sites-enabled/default
fi
nginx -t
systemctl reload nginx

# ---------------------------------------------------------------- backups + helper commands
say "Scheduling the nightly database backup (11:30 PM, keeps 14 days)"
rm -f /usr/local/sbin/dental-haven-backup; install -m 755 "$HERE/backup.sh" /usr/local/sbin/dental-haven-backup
sed -i "s|^DATA_DIR=.*|DATA_DIR=\"$DATA_DIR\"|; s|^BACKUP_DIR=.*|BACKUP_DIR=\"$BACKUP_DIR\"|" /usr/local/sbin/dental-haven-backup
echo "30 23 * * * root /usr/local/sbin/dental-haven-backup >/dev/null 2>&1" > /etc/cron.d/dental-haven-backup
chmod 644 /etc/cron.d/dental-haven-backup
bash "$HERE/install-commands.sh"

# ---------------------------------------------------------------- check the app answers
say "Checking that the system is running"
ok=0
for _ in $(seq 1 30); do
  if curl -fs -o /dev/null http://127.0.0.1:8000/; then ok=1; break; fi
  sleep 2
done
[ "$ok" -eq 1 ] || die "The system didn't start. Show the error with:  journalctl -u dental-haven -n 50 --no-pager"
echo "The system is running."

# ---------------------------------------------------------------- HTTPS
echo "$LE_EMAIL" > "$ENV_DIR/letsencrypt-email"; chmod 600 "$ENV_DIR/letsencrypt-email"
echo "$NAMES" > "$ENV_DIR/server-names"; chmod 644 "$ENV_DIR/server-names"
if [ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]; then
  echo "HTTPS certificate already present."
else
  bash "$HERE/enable-https.sh" || warn "HTTPS isn't on yet. When the domain points to this server, run:  dental-haven-https"
fi

IP="$(hostname -I | awk '{print $1}')"
say "Done"
cat <<EOF
  Open:   https://$DOMAIN/staff/login
  Sign in with the clinic owner's email and the temporary password, then choose a new password.

  Useful commands (type them in this Console):
    dental-haven-update            get the newest version from GitHub and restart
    dental-haven-https             turn on HTTPS (if it wasn't ready above)
    dental-haven-backup            make a database backup right now
    systemctl restart dental-haven restart the system
    journalctl -u dental-haven -n 50 --no-pager   show recent errors

  This server's IP address: $IP
EOF
