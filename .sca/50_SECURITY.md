# セキュリティ設定（fail2ban + /health内部専用化）

## fail2ban 導入（SSH + nginx 最低限）

### 1. インストール

```bash
sudo apt update
sudo apt install -y fail2ban
```

### 2. 基本設定（jail.local 作成）

```bash
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local
```

### 3. SSH 保護（必須）

`/etc/fail2ban/jail.local` を編集：

```ini
[sshd]
enabled = true
port    = ssh
logpath = %(sshd_log)s
maxretry = 5
findtime = 10m
bantime  = 1h
```

### 4. nginx スキャン対策（超重要）

同じファイルに追加：

```ini
[nginx-botsearch]
enabled  = true
logpath  = /var/log/nginx/access.log
maxretry = 2
findtime = 10m
bantime  = 24h
```

**注意：** これで `/cgi-bin /wp-login.php /.env /.git` みたいな世界共通のゴミスキャンは即BANされる。

### 5. 再起動＆確認

```bash
sudo systemctl restart fail2ban
sudo systemctl enable fail2ban
sudo fail2ban-client status
sudo fail2ban-client status sshd
```

---

## /health を内部専用に固定（Nginx）

**外部公開しない判断は正解。** Nginx で 127.0.0.1 のみ許可する。

### Nginx 設定例（location /health）

Nginx設定ファイル（例：`/etc/nginx/sites-available/singkana`）に追加：

```nginx
location /health {
    allow 127.0.0.1;
    deny all;
    proxy_pass http://127.0.0.1:5000/health;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
}
```

### 反映

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 確認

```bash
# VPS内（OK）
curl http://127.0.0.1/health

# 外部（403 or deny）
curl https://singkana.com/health
```

---

## 確認コマンド

### fail2ban状態確認

```bash
# 全体的な状態
sudo fail2ban-client status

# SSH jailの状態
sudo fail2ban-client status sshd

# nginx jailの状態（設定した場合）
sudo fail2ban-client status nginx-botsearch

# 現在BANされているIP
sudo fail2ban-client status sshd | grep "Banned IP list"
```

### /healthアクセス確認

```bash
# 内部からのアクセス（200 OKが返る）
curl -s http://127.0.0.1/health | python3 -m json.tool

# 外部からのアクセス（403 Forbiddenが返る）
curl -I https://singkana.com/health
```

---

## 注意事項

- **fail2banは誤検知の可能性があるため、定期的にBANリストを確認**
- **/healthは内部専用のため、外部からはアクセスできない**
- **secrets.envの権限は現状維持（600 root:root）**
