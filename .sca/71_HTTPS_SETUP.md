# HTTPS設定（本番環境）

## 現状確認

### 本番環境（singkana.com）
- **HTTPS必須**: `.sca/30_DEV_PROD.md` に記載
- **Nginx + Let's Encrypt**: `setup_singkana_example.sh` にcertbot設定あり
- **COOKIE_SECURE=1**: 本番環境で有効化

### ローカル開発環境（127.0.0.1:5000）
- **HTTP使用**: 正常（開発環境ではHTTPS不要）
- **警告表示**: ブラウザの正常な動作
- **修正不要**: 開発環境では問題なし

---

## ローカル開発環境での警告を消す方法（オプション）

### 方法1: ブラウザ設定で警告を無効化（推奨）

**Chrome/Edge:**
1. アドレスバー左の「保護されていません」をクリック
2. 「このサイトの設定」→「localhostへの警告を無効にする」を有効化

**Firefox:**
- ローカルホストへの警告は表示されない（デフォルト）

### 方法2: ローカル開発環境でHTTPSを使う（通常不要）

自己署名証明書を使用（開発環境のみ）：

```bash
# 証明書生成（初回のみ）
openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365 -subj "/CN=localhost"

# Flask起動時にHTTPS指定（.vscode/tasks.jsonを変更）
# ただし、通常は不要（HTTPで十分）
```

**注意**: 開発環境でHTTPSを使う必要はありません。本番環境でHTTPSが有効になっていれば問題ありません。

---

## 本番環境のHTTPS確認方法

### VPSで確認

```bash
# SSL証明書の確認
sudo certbot certificates

# Nginx設定の確認
sudo nginx -t
sudo cat /etc/nginx/sites-available/singkana

# HTTPS接続テスト
curl -I https://singkana.com
```

### 期待される結果

```bash
# HTTPS接続が成功
HTTP/2 200
strict-transport-security: max-age=31536000
```

---

## 本番環境のNginx設定（参考）

### 基本的なHTTPS設定

```nginx
server {
    listen 80;
    server_name singkana.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name singkana.com;

    ssl_certificate /etc/letsencrypt/live/singkana.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/singkana.com/privkey.pem;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    
    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## トラブルシューティング

### 本番環境でHTTPSが動作しない場合

1. **証明書の確認**
   ```bash
   sudo certbot certificates
   ```

2. **証明書の更新**
   ```bash
   sudo certbot renew
   ```

3. **Nginx設定の確認**
   ```bash
   sudo nginx -t
   sudo systemctl reload nginx
   ```

4. **ファイアウォールの確認**
   ```bash
   sudo ufw status
   # 443ポートが開いているか確認
   ```

---

## まとめ

- **ローカル開発環境（127.0.0.1:5000）**: HTTP使用は正常、警告は無視してOK
- **本番環境（singkana.com）**: HTTPS必須、Let's Encryptで証明書取得済み
- **修正不要**: ローカル開発環境での警告は正常な動作
