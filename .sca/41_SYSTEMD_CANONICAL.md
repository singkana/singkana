# systemd設定の正規化（Canonical）

## 正規化された設定

**ファイル：** `/etc/systemd/system/singkana.service`

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
Environment=SINGKANA_LOG_DIR=/var/log/singkana
ExecStart=/var/www/singkana/venv/bin/gunicorn --bind 127.0.0.1:5000 --workers 2 app_web:app
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

## 重要なポイント

### WorkingDirectory
- **固定値：** `/var/www/singkana`
- **理由：** systemd実態に合わせる

### EnvironmentFile
- **固定値：** `/etc/singkana/secrets.env`
- **理由：** 秘密情報をGit外で管理

### ExecStart
- **固定値：** `/var/www/singkana/venv/bin/gunicorn --bind 127.0.0.1:5000 --workers 2 app_web:app`（1行形式）
- **理由：** 改行（バックスラッシュ）は環境によって解釈が不安定なため1行に統一。workersは2で安全側に設定

### 環境変数の分離

**Git管理しない（secrets.env）：**
- `OPENAI_API_KEY`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PUBLISHABLE_KEY`
- `STRIPE_PRICE_PRO_MONTHLY`
- `STRIPE_PRICE_PRO_YEARLY`
- `APP_BASE_URL`
- `COOKIE_SECURE`（本番のみ `1`、DEVは `0`）
- `SINGKANA_DB_PATH`

**DB分離：**
- `SINGKANA_DB_PATH=/var/lib/singkana/singkana.db`
- シンボリックリンク不要（環境変数で分離）

## 適用方法

```bash
# 設定ファイルを編集
sudo nano /etc/systemd/system/singkana.service

# 変更を反映
sudo systemctl daemon-reload

# サービス再起動
sudo systemctl restart singkana

# 状態確認
sudo systemctl status singkana --no-pager
```

## 確認コマンド

```bash
# 設定の確認
sudo systemctl cat singkana.service

# 環境変数の確認
sudo systemctl show singkana | grep EnvironmentFile

# 実際に読み込まれている環境変数（デバッグ用）
sudo -u www-data bash -c 'source /etc/singkana/secrets.env && env | grep -E "(STRIPE|APP_BASE|SINGKANA_DB)"'
```
