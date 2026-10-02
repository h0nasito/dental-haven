#!/usr/bin/env bash
# Turn on HTTPS with a free Let's Encrypt certificate (renews itself). Run as root:  dental-haven-https
# Works only after the domain's DNS points to this server.
set -euo pipefail
NAMES="$(cat /etc/dental-haven/server-names)"
EMAIL="$(cat /etc/dental-haven/letsencrypt-email 2>/dev/null || true)"
IP="$(hostname -I | awk '{print $1}')"
for n in $NAMES; do
  got="$(getent ahostsv4 "$n" | awk 'NR==1{print $1}')"
  if [ "$got" != "$IP" ]; then
    echo "$n points to '${got:-nothing}', not this server ($IP)."
    echo "Fix the DNS A record, wait 10-30 minutes, then run:  dental-haven-https"
    exit 1
  fi
done
args=(); for n in $NAMES; do args+=(-d "$n"); done
if [ -n "$EMAIL" ]; then mail=(--email "$EMAIL"); else mail=(--register-unsafely-without-email); fi
certbot --nginx --non-interactive --agree-tos --redirect "${mail[@]}" "${args[@]}"
systemctl reload nginx
echo "HTTPS is on: https://${NAMES%% *}"
