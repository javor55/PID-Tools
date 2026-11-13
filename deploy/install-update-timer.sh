#!/usr/bin/env bash
# Automatická aktualizace PID Tools na VM: systemd časovač každých 5 minut stáhne obraz :deploy z GHCR a pokud je nový,
# restartuje kontejner app (docker compose up -d mění jen kontejnery se změněným obrazem). Nahrazuje Watchtower –
# žádný cizí kontejner nedostane přístup k Docker socketu.
#
# Spusťte jednou ve složce deploy (jako uživatel ve skupině docker, skript si sám řekne o sudo):
#   ./install-update-timer.sh
# Stav:      systemctl list-timers pidtools-update.timer ; journalctl -u pidtools-update.service -n 50
# Vypnutí:   sudo systemctl disable --now pidtools-update.timer
set -euo pipefail

dir="$(cd "$(dirname "$0")" && pwd)"
user="${SUDO_USER:-$(id -un)}"
docker_bin="$(command -v docker)"
interval="${1:-5min}"

[ -f "$dir/compose.yml" ] || { echo "compose.yml není v $dir" >&2; exit 1; }
[ -f "$dir/.env" ] || { echo "chybí $dir/.env (cp .env.example .env a doplňte TUNNEL_TOKEN)" >&2; exit 1; }

sudo tee /etc/systemd/system/pidtools-update.service >/dev/null <<EOF
[Unit]
Description=PID Tools – stažení nové verze obrazu a restart aplikace
Wants=network-online.target
After=network-online.target docker.service

[Service]
Type=oneshot
User=$user
WorkingDirectory=$dir
ExecStart=$docker_bin compose pull --quiet app
ExecStart=$docker_bin compose up -d --remove-orphans
ExecStartPost=$docker_bin image prune -f
EOF

sudo tee /etc/systemd/system/pidtools-update.timer >/dev/null <<EOF
[Unit]
Description=PID Tools – kontrola nové verze každých $interval

[Timer]
OnBootSec=2min
OnUnitActiveSec=$interval
RandomizedDelaySec=30
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now pidtools-update.timer
echo "Hotovo: pidtools-update.timer běží (uživatel $user, složka $dir, interval $interval)."
systemctl list-timers pidtools-update.timer --no-pager || true
