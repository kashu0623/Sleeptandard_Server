#!/usr/bin/env bash
set -Eeuo pipefail

DOMAIN="${HTTPS_DOMAIN:-}"
EMAIL="${LETSENCRYPT_EMAIL:-}"

if [[ -z "$DOMAIN" ]]; then
    echo "HTTPS_DOMAIN is empty; skipping HTTPS configuration."
    exit 0
fi

if [[ -z "$EMAIL" ]]; then
    echo "LETSENCRYPT_EMAIL is empty; skipping HTTPS configuration."
    exit 0
fi

dnf install -y certbot

mkdir -p /var/www/letsencrypt

cat > /etc/nginx/conf.d/10_api_dev_http.conf <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/letsencrypt;
        default_type text/plain;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 60s;
        client_max_body_size 100m;
    }
}
EOF

nginx -t
systemctl reload nginx

certbot certonly \
    --webroot \
    --webroot-path /var/www/letsencrypt \
    --non-interactive \
    --agree-tos \
    --no-eff-email \
    --keep-until-expiring \
    --email "$EMAIL" \
    --domains "$DOMAIN"

cat > /etc/nginx/conf.d/10_api_dev_http.conf <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    location ^~ /.well-known/acme-challenge/ {
        root /var/www/letsencrypt;
        default_type text/plain;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}
EOF

cat > /etc/nginx/conf.d/20_api_dev_https.conf <<EOF
server {
    listen 443 ssl;
    server_name $DOMAIN;

    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 60s;
        client_max_body_size 100m;
    }
}
EOF

cat > /etc/systemd/system/sleeptandard-certbot-renew.service <<'EOF'
[Unit]
Description=Renew Sleeptandard Let's Encrypt certificate
After=network-online.target nginx.service

[Service]
Type=oneshot
ExecStart=/usr/bin/certbot renew --quiet --no-random-sleep-on-renew --deploy-hook "/usr/bin/systemctl reload nginx"
EOF

cat > /etc/systemd/system/sleeptandard-certbot-renew.timer <<'EOF'
[Unit]
Description=Run Sleeptandard certificate renewal daily

[Timer]
OnCalendar=daily
RandomizedDelaySec=6h
Persistent=true

[Install]
WantedBy=timers.target
EOF

nginx -t
systemctl reload nginx
systemctl daemon-reload
systemctl enable --now sleeptandard-certbot-renew.timer
