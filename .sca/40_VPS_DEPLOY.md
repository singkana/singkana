# VPS Git Pull専用デプロイ手順（最終確定版）

## 大原則
- **VPSでは編集しない**（pullして再起動するだけ）
- **コードはGit管理**
- **秘密情報・DB・ログ・アップロードはGit管理しない**
- **デプロイは deployユーザーで実行（www-dataは実行ユーザーのみ）**

---

## 初回セットアップ（VPS側・コピペ実行）

**前提：** root か sudo できるユーザーで入ってること。

### 0) いま動いてるサービス止める（安全）

```bash
sudo systemctl stop singkana || true
```

### 1) deployユーザー作成

```bash
sudo adduser --disabled-password --gecos "" deploy
```

### 2) deployのSSH鍵作成 → 公開鍵を表示

```bash
sudo -iu deploy
mkdir -p ~/.ssh && chmod 700 ~/.ssh
ssh-keygen -t ed25519 -C "singkana@vps" -f ~/.ssh/id_ed25519
cat ~/.ssh/id_ed25519.pub
```

**ここで出た公開鍵を GitHub repo → Settings → Deploy keys に登録：**
- Title: `vps-deploy`
- ✅ Allow write access **OFF**

登録後、VPSに戻って：

```bash
ssh -T git@github.com
exit
```

### 3) 既存コード退避 → clone

```bash
cd /var/www
sudo mv singkana "singkana_OLD_$(date +%Y%m%d_%H%M%S)" 2>/dev/null || true
sudo chown -R deploy:deploy /var/www
sudo -iu deploy bash -lc 'cd /var/www && git clone git@github.com:singkana/singkana.git singkana'
```

### 4) secrets（Git外）作成

```bash
sudo mkdir -p /etc/singkana
sudo nano /etc/singkana/secrets.env
sudo chmod 600 /etc/singkana/secrets.env
sudo chown root:root /etc/singkana/secrets.env
```

**secrets.env の内容（最低限）：**

```env
OPENAI_API_KEY=...
APP_BASE_URL=https://singkana.com

SINGKANA_DB_PATH=/var/lib/singkana/singkana.db
BILLING_DB_PATH=/var/lib/singkana/billing.db
COOKIE_SECURE=1
```

**注意：** `COOKIE_SECURE=1` は本番環境のみ。DEV環境では `0` を使用。

### 5) 永続データ置き場（www-dataが書く）

```bash
sudo mkdir -p /var/lib/singkana /var/log/singkana
sudo chown -R www-data:www-data /var/lib/singkana /var/log/singkana
```

**既存DBがあるなら移動：**

```bash
sudo mv /var/www/singkana_OLD_*/singkana.db /var/lib/singkana/singkana.db 2>/dev/null || true
sudo mv /var/www/singkana_OLD_*/billing.db  /var/lib/singkana/billing.db  2>/dev/null || true
sudo chown www-data:www-data /var/lib/singkana/*.db 2>/dev/null || true
```

### 6) venv作成（deployが作る）

```bash
sudo -iu deploy bash -lc 'cd /var/www/singkana && python3 -m venv venv && source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt'
```

### 7) systemdを正規化（ExecStartは1行）

**まず現状確認：**

```bash
sudo systemctl cat singkana.service
```

**必要なら `/etc/systemd/system/singkana.service` をこうする：**

```ini
[Unit]
Description=SingKANA Gunicorn Service
After=network.target

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
sudo systemctl restart singkana
sudo systemctl status singkana --no-pager
```

**ログ確認（失敗時はこれが真実）：**

```bash
sudo journalctl -u singkana -n 200 --no-pager
```

---

## 通常のデプロイ（以後これだけ・pull専用）

**VPSでは編集せず、deployユーザーでこれだけ実行：**

```bash
sudo -iu deploy bash -lc 'cd /var/www/singkana && git pull'
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
sudo -iu deploy ssh -T git@github.com

# 権限確認（deploy所有であることを確認）
ls -la /var/www/singkana/.git
# 所有者が deploy:deploy であることを確認

# もし所有者が違う場合は修正
sudo chown -R deploy:deploy /var/www/singkana
```

### サービスが起動しない
```bash
# 詳細ログを確認
sudo journalctl -u singkana -n 200 --no-pager

# venvの確認
ls -la /var/www/singkana/venv/bin/gunicorn

# 環境変数の確認
sudo -u www-data bash -c 'cd /var/www/singkana && source /etc/singkana/secrets.env && env | grep -E "(SINGKANA_DB|APP_BASE)"'
```

---

## 診断用ログ（これだけで診断できる）

問題が発生した場合、以下を確認：

1. **SSH接続確認：**
   ```bash
   sudo -iu deploy ssh -T git@github.com
   ```

2. **サービス状態：**
   ```bash
   sudo systemctl status singkana --no-pager
   ```

3. **詳細ログ（失敗時）：**
   ```bash
   sudo journalctl -u singkana -n 200 --no-pager
   ```

---

## 注意事項

- **VPSでの手編集は禁止**
- **git pull と systemctl restart 以外は実行しない**
- **secrets.env は絶対にGitにコミットしない**
- **DBファイルは /var/lib/singkana/ に配置（Git外）**
- **デプロイは deployユーザーで実行（www-dataは実行ユーザーのみ）**
- **/var/www/singkana は deploy所有、/var/lib/singkana と /var/log/singkana は www-data所有**
