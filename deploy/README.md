# Деплой на свой VPS (Ubuntu) — всегда онлайн, с HTTPS

Быстрый путь для сервера Ubuntu 22.04/24.04. Все команды — от root.

## 1. Система и код
```bash
apt update
apt install -y python3 python3-venv python3-pip git
git clone -b claude/hello-kx9ups https://github.com/eldarmemetov1221-hub/AI.git /opt/agent
cd /opt/agent
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

## 2. Ключи
Создай `/opt/agent/agent.env` (см. `.env.example`) c LLM_API_KEY, MODEL_ID,
LLM_BASE_URL, LEAD_WEBHOOK_URL, ALLOWED_ORIGINS.

## 3. Служба (автозапуск)
```bash
cp /opt/agent/deploy/agent.service /etc/systemd/system/agent.service
systemctl daemon-reload
systemctl enable --now agent
systemctl status agent      # active (running)
curl http://127.0.0.1:8000/health
```

## 4. HTTPS через Caddy
```bash
apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt update
apt install -y caddy
cp /opt/agent/deploy/Caddyfile /etc/caddy/Caddyfile   # поправь домен под свой IP
systemctl restart caddy
```

Открой `https://<твой-ip>.sslip.io` — должна открыться демо-страница с чатом.

## Обновление кода позже
```bash
cd /opt/agent && git pull
systemctl restart agent
```
