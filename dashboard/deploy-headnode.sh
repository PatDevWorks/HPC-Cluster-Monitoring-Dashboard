#!/usr/bin/env bash
# Deploy Sol Plaatje A Dev Cluster Dashboard v2.0 as a 24/7 systemd service on Ubuntu 24.04 Head Node
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_USER="${SUDO_USER:-$USER}"

echo "[1/4] Building React frontend production bundle..."
cd "$APP_DIR/frontend"
npm install
npm run build

echo "[2/4] Setting up Python virtual environment..."
cd "$APP_DIR/backend"
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt

echo "[3/4] Writing /etc/systemd/system/spu-hpc-aiops.service ..."
sudo tee /etc/systemd/system/spu-hpc-aiops.service >/dev/null <<EOF
[Unit]
Description=Sol Plaatje A Dev Cluster Dashboard
After=network.target prometheus.service

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${APP_DIR}/backend
Environment="PROMETHEUS_URL=http://localhost:9090"
Environment="GRAFANA_URL=http://localhost:3000"
ExecStart=${APP_DIR}/backend/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "[4/4] Enabling and starting spu-hpc-aiops.service ..."
sudo systemctl daemon-reload
sudo systemctl enable --now spu-hpc-aiops.service
sudo systemctl status spu-hpc-aiops.service --no-pager -l
echo "Deployment complete! Platform is live on port 8000."
