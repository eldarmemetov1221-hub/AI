#!/usr/bin/env bash
# Устанавливает Caddy (бесплатный HTTPS) и проксирует его на агента.
# Запуск:  bash /opt/agent/deploy/install-caddy.sh
set -e

echo ">>> Installing Caddy..."
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl gnupg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update
apt install -y caddy

echo ">>> Applying Caddyfile..."
cp /opt/agent/deploy/Caddyfile /etc/caddy/Caddyfile
systemctl enable caddy
systemctl restart caddy

echo ">>> Done. In ~30 seconds open: https://147.45.178.223.sslip.io"
