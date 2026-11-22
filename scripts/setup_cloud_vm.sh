#!/usr/bin/env bash
# ==============================================================================
# One-Command Cloud VM Provisioning Script for Ubuntu/Debian Linux
# (Works on AWS EC2 Free Tier, Oracle Cloud Always-Free, GCP, or DigitalOcean)
#
# This runs 100% on the cloud server. Your local computer has ZERO load.
# ==============================================================================
set -e

echo "=== Physics Wallah Cloud VM Provisioning ==="

# 1. Update system packages
sudo apt update && sudo apt install -y python3 python3-pip python3-venv git curl sqlite3 nginx certbot python3-certbot-nginx

# 2. Set up working directory
APP_DIR="/opt/pw-gate-predictor"
if [ ! -d "$APP_DIR" ]; then
    echo "Cloning repository..."
    sudo git clone https://github.com/physicswallah/Rank-and-College-Predictor-Tool.git "$APP_DIR"
fi

cd "$APP_DIR"

# 3. Create virtual environment
sudo python3 -m venv .venv
sudo "$APP_DIR/.venv/bin/pip" install --upgrade pip
sudo "$APP_DIR/.venv/bin/pip" install -r requirements.txt

# 4. Set directory permissions
sudo chown -R www-data:www-data "$APP_DIR"

# 5. Create Systemd Service for automatic 24/7 background running
echo "Configuring Systemd service..."
sudo tee /etc/systemd/system/gate-predictor.service > /dev/null <<EOF
[Unit]
Description=Physics Wallah GATE Predictor Service
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/opt/pw-gate-predictor
ExecStart=/opt/pw-gate-predictor/.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 4 --proxy-headers
Restart=always
RestartSec=3
Environment="DATABASE_URL=sqlite:////opt/pw-gate-predictor/gate_predictor.db"

[Install]
WantedBy=multi-user.target
EOF

# 6. Enable and start background service
sudo systemctl daemon-reload
sudo systemctl enable gate-predictor
sudo systemctl restart gate-predictor

# 7. Configure Nginx Reverse Proxy
echo "Configuring Nginx..."
sudo tee /etc/nginx/sites-available/gate-predictor > /dev/null <<EOF
server {
    listen 80;
    server_name _;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

sudo ln -sf /etc/nginx/sites-available/gate-predictor /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

echo "=== Cloud VM Setup Complete! ==="
echo "The application is now running 24/7 in the cloud at: http://$(curl -s ifconfig.me)"
echo "Zero load on your local machine. Check logs anytime on the server with:"
echo "sudo journalctl -u gate-predictor -f"
