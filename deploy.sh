#!/usr/bin/env bash
# ============================================================
# deploy.sh — быстрый деплой на VPS (Ubuntu 22.04 / 24.04)
# Запускать от root или через sudo:
#   chmod +x deploy.sh && sudo ./deploy.sh
# ============================================================

set -euo pipefail

APP_DIR="/opt/smart-search"
APP_USER="smartsearch"
PYTHON_VERSION="3.12"

echo "=== 1. Системные зависимости ==="
apt-get update -qq
apt-get install -y -qq python${PYTHON_VERSION} python${PYTHON_VERSION}-venv python${PYTHON_VERSION}-dev git nginx

echo "=== 2. Пользователь и папка ==="
id -u $APP_USER &>/dev/null || useradd -r -m -s /bin/bash $APP_USER
mkdir -p $APP_DIR
cp -r . $APP_DIR/
chown -R $APP_USER:$APP_USER $APP_DIR

echo "=== 3. Python virtualenv ==="
sudo -u $APP_USER bash -c "
  cd $APP_DIR
  python${PYTHON_VERSION} -m venv venv
  source venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
"

echo "=== 4. Скачивание модели E5-large (1.2 ГБ) ==="
sudo -u $APP_USER bash -c "
  cd $APP_DIR && source venv/bin/activate
  python -c \"from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-large'); print('Model OK')\"
"

echo "=== 5. Systemd: FastAPI ==="
cat > /etc/systemd/system/smart-search-api.service << 'EOF'
[Unit]
Description=Smart Search FastAPI
After=network.target

[Service]
Type=simple
User=smartsearch
WorkingDirectory=/opt/smart-search
Environment=STORAGE_BACKEND=memory
Environment=SEED_DEMO_DATA=true
ExecStart=/opt/smart-search/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "=== 6. Systemd: Streamlit ==="
cat > /etc/systemd/system/smart-search-ui.service << 'EOF'
[Unit]
Description=Smart Search Streamlit UI
After=smart-search-api.service

[Service]
Type=simple
User=smartsearch
WorkingDirectory=/opt/smart-search
Environment=STORAGE_BACKEND=memory
Environment=SEED_DEMO_DATA=true
ExecStart=/opt/smart-search/venv/bin/streamlit run streamlit_app.py --server.port=8501 --server.address=127.0.0.1 --server.headless=true
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "=== 7. Nginx reverse proxy ==="
cat > /etc/nginx/sites-available/smart-search << 'NGINX'
server {
    listen 80;
    server_name _;

    # API: your-vps-ip/api/...
    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Streamlit UI: your-vps-ip/ (main page)
    location / {
        proxy_pass http://127.0.0.1:8501/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
NGINX

ln -sf /etc/nginx/sites-available/smart-search /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

echo "=== 8. Запуск ==="
systemctl daemon-reload
systemctl enable --now smart-search-api smart-search-ui
systemctl restart nginx

echo ""
echo "============================================"
echo " ГОТОВО!"
echo " Streamlit UI:  http://YOUR_VPS_IP/"
echo " API Docs:      http://YOUR_VPS_IP/api/docs"
echo " API Health:    http://YOUR_VPS_IP/api/health"
echo "============================================"
