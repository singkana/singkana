#!/usr/bin/env bash
# SingKANA 用 簡易セットアップスクリプト（必要に応じて編集して使ってください）

set -e

APP_DIR="/srv/singkana"
ZIP_PATH="./singkana_beta2_feedback_vps.zip"  # VPS 上での zip 位置に合わせて変更
DOMAIN="example.com"      # ここを書き換え
EMAIL="you@example.com"   # certbot 用メール
OPENAI_API_KEY_VALUE="YOUR_OPENAI_API_KEY_HERE"

apt-get update -y
apt-get install -y python3-venv python3-pip nginx unzip certbot python3-certbot-nginx

mkdir -p "${APP_DIR}"
unzip -o "${ZIP_PATH}" -d "${APP_DIR}"

cd "${APP_DIR}"
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

cat > .env <<EOF
OPENAI_API_KEY=${OPENAI_API_KEY_VALUE}
SINGKANA_MODEL=gpt-5.1-mini
EOF

cat > /etc/systemd/system/singkana.service <<EOF
[Unit]
Description=SingKANA Flask app via gunicorn
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=${APP_DIR}
Environment="PATH=${APP_DIR}/.venv/bin"
EnvironmentFile=${APP_DIR}/.env
ExecStart=${APP_DIR}/.venv/bin/gunicorn -w 3 -b 127.0.0.1:8000 app_web:app
Restart=always

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/nginx/sites-available/singkana.conf <<EOF
server {
    listen 80;
    server_name ${DOMAIN};

    client_max_body_size 20M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
EOF

ln -sf /etc/nginx/sites-available/singkana.conf /etc/nginx/sites-enabled/singkana.conf
nginx -t
systemctl reload nginx

systemctl daemon-reload
systemctl enable singkana
systemctl start singkana

certbot --nginx -d "${DOMAIN}" -m "${EMAIL}" --agree-tos --redirect --non-interactive

echo "セットアップ完了。 https://${DOMAIN} にアクセスして動作確認してください。"
