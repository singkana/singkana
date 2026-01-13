# VPS Git Pull専用デプロイ手順

## 大原則
- **VPSでは編集しない**（pullして再起動するだけ）
- **コードはGit管理**
- **秘密情報・DB・ログ・アップロードはGit管理しない**

---

## 初回セットアップ（VPS側）

### 1. 既存コードを退避（保険）

```bash
sudo systemctl stop singkana || true
cd /var/www
sudo mv singkana singkana_OLD_$(date +%Y%m%d_%H%M%S)
```

### 2. deployユーザーを作成（デプロイ専用）

```bash
# deployユーザーを作成（既に存在する場合はスキップ）
sudo useradd -m -s /bin/bash deploy || true

# deployユーザーをsudoグループに追加（systemctl restart用）
sudo usermod -aG sudo deploy
```

### 3. リポジトリをクローン（deployユーザー所有）

```bash
cd /var/www
sudo git clone <YOUR_REPO_SSH_URL> singkana
sudo chown -R deploy:deploy /var/www/singkana
cd /var/www/singkana
```

### 4. 秘密情報を分離（Git外）

```bash
# secrets.env を作成
sudo mkdir -p /etc/singkana
sudo nano /etc/singkana/secrets.env
```

**secrets.env の内容例：**
```
OPENAI_API_KEY=...
STRIPE_SECRET_KEY=...
STRIPE_WEBHOOK_SECRET=...
STRIPE_PUBLISHABLE_KEY=...
STRIPE_PRICE_PRO_MONTHLY=...
STRIPE_PRICE_PRO_YEARLY=...
APP_BASE_URL=https://singkana.com
COOKIE_SECURE=1
SINGKANA_DB_PATH=/var/lib/singkana/singkana.db
```

**注意：** `COOKIE_SECURE=1` は本番環境のみ。DEV環境では `0` を使用。
```

**権限を締める：**
```bash
sudo chmod 600 /etc/singkana/secrets.env
sudo chown root:root /etc/singkana/secrets.env
```

### 5. DB/ログの置き場を固定（Git外・www-data所有）

```bash
# 永続データ用ディレクトリ作成
sudo mkdir -p /var/lib/singkana /var/log/singkana
sudo chown -R www-data:www-data /var/lib/singkana /var/log/singkana
```

**既存DBがある場合の移行：**
```bash
cd /var/www/singkana
if [ -f singkana.db ]; then
    sudo mv singkana.db /var/lib/singkana/singkana.db
fi
if [ -f billing.db ]; then
    sudo mv billing.db /var/lib/singkana/billing.db
fi
```

### 6. Python環境を作成（deployユーザーで実行）

```bash
cd /var/www/singkana
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 7. systemd設定の正規化

**`/etc/systemd/system/singkana.service` を確認・更新：**

```ini
[Unit]
Description=SingKANA Gunicorn Service
After=network.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/singkana
EnvironmentFile=/etc/singkana/secrets.env
ExecStart=/var/www/singkana/venv/bin/gunicorn --bind 127.0.0.1:5000 --workers 2 app_web:app
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

**適用：**
```bash
sudo systemctl daemon-reload
sudo systemctl enable singkana
sudo systemctl start singkana
sudo systemctl status singkana --no-pager
```

---

## 通常のデプロイ（以後これだけ）

**VPSでは編集せず、deployユーザーでこれだけ実行：**

```bash
# deployユーザーでログインして実行
cd /var/www/singkana
git pull
sudo systemctl restart singkana
sudo systemctl status singkana --no-pager
```

**それ以外は禁止。**

---

## 環境変数の確認

アプリが正しく環境変数を読んでいるか確認：

```bash
sudo systemctl show singkana | grep EnvironmentFile
# 出力: EnvironmentFile=/etc/singkana/secrets.env

# 実際に読み込まれているか確認（デバッグ用）
sudo -u www-data bash -c 'source /etc/singkana/secrets.env && env | grep -E "(STRIPE|APP_BASE|SINGKANA_DB)"'
```

---

## トラブルシューティング

### DBが見つからない
```bash
# 環境変数が正しく設定されているか確認
sudo -u www-data bash -c 'echo $SINGKANA_DB_PATH'
# 出力: /var/lib/singkana/singkana.db

# DBファイルの存在確認
ls -la /var/lib/singkana/
```

### secrets.envが読まれない
```bash
# systemd設定を確認
sudo systemctl cat singkana.service | grep EnvironmentFile
# 出力に EnvironmentFile=/etc/singkana/secrets.env があることを確認

# 権限確認
ls -la /etc/singkana/secrets.env
# 出力: -rw------- 1 root root ... (600であること)
```

### Git pullが失敗する
```bash
# SSH鍵の確認（deployユーザーで実行）
sudo -u deploy ssh -T git@github.com

# 権限確認（deploy所有であることを確認）
ls -la /var/www/singkana/.git
# 所有者が deploy:deploy であることを確認

# もし所有者が違う場合は修正
sudo chown -R deploy:deploy /var/www/singkana
```

---

## 注意事項

- **VPSでの手編集は禁止**
- **git pull と systemctl restart 以外は実行しない**
- **secrets.env は絶対にGitにコミットしない**
- **DBファイルは /var/lib/singkana/ に配置（Git外）**
