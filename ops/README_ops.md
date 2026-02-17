# SingKANA 運用スクリプト (`ops/`)

## ファイル一覧

| ファイル | 用途 |
|----------|------|
| `cleanup_db.sh` | DB の期限切れレコード掃除（1日1回） |
| `backup_full_encrypted.sh` | フルバックアップ作成 + GPG暗号化 + SHA256生成 |
| `singkana-backup-encrypted.service` | 暗号化フルバックアップの systemd service |
| `singkana-backup-encrypted.timer` | 暗号化フルバックアップの日次 timer |
| `logrotate-singkana.conf` | ログローテーション定義 |
| `singkana-cleanup.service` | cleanup の systemd service unit |
| `singkana-cleanup.timer` | cleanup の systemd timer（cron代替） |

---

## 1. DB Cleanup のセットアップ

### Option A: cron（最もシンプル）

```bash
# www-data ユーザーの crontab に追加
sudo crontab -u www-data -e
```

以下を追記:

```cron
# SingKANA DB cleanup — 毎日 AM 4:00 (JST)
0 4 * * * /var/www/singkana/ops/cleanup_db.sh --verbose >> /var/log/singkana/cleanup.log 2>&1
```

### Option B: systemd timer（推奨: ログが journalctl に統合される）

```bash
# unit ファイルを配置
sudo cp /var/www/singkana/ops/singkana-cleanup.service /etc/systemd/system/
sudo cp /var/www/singkana/ops/singkana-cleanup.timer   /etc/systemd/system/

# 有効化 & 開始
sudo systemctl daemon-reload
sudo systemctl enable --now singkana-cleanup.timer

# 確認
sudo systemctl list-timers | grep singkana
sudo journalctl -u singkana-cleanup.service --no-pager -n 20
```

### 手動テスト

```bash
# dry-run（削除せず件数表示）
sudo -u www-data /var/www/singkana/ops/cleanup_db.sh --dry-run --verbose

# 実行
sudo -u www-data /var/www/singkana/ops/cleanup_db.sh --verbose
```

---

## 2. Logrotate のセットアップ

```bash
# ログディレクトリ作成
sudo mkdir -p /var/log/singkana
sudo chown www-data:www-data /var/log/singkana

# logrotate 設定を配置
sudo cp /var/www/singkana/ops/logrotate-singkana.conf /etc/logrotate.d/singkana

# dry-run 確認
sudo logrotate --debug /etc/logrotate.d/singkana

# 強制実行テスト
sudo logrotate --force /etc/logrotate.d/singkana
```

### Gunicorn にログ出力先を指定する

systemd の `ExecStart` を更新:

```ini
ExecStart=/var/www/singkana/venv/bin/gunicorn \
    --bind 127.0.0.1:5000 \
    --workers 2 \
    --access-logfile /var/log/singkana/gunicorn-access.log \
    --error-logfile /var/log/singkana/gunicorn-error.log \
    app_web:app
```

反映:

```bash
sudo systemctl daemon-reload
sudo systemctl restart singkana
```

---

## 3. KPI 日次集計（簡易）

```bash
# 当日のステータスコード別集計
grep "$(date +%Y-%m-%d)" /var/log/singkana/sheet_api.access.log \
  | awk '{print $9}' | sort | uniq -c | sort -rn

# Stripe checkout.session.completed 件数
sudo journalctl -u singkana --since today --no-pager \
  | grep -c "checkout.session.completed" || echo 0
```

---

## 4. 前提: ログディレクトリ & 権限

```bash
sudo mkdir -p /var/log/singkana /run/singkana
sudo chown www-data:www-data /var/log/singkana /run/singkana
```

---

## 5. 暗号化フルバックアップ（推奨: systemd timer 運用）

```bash
# 実行権限（初回のみ）
sudo chmod +x /var/www/singkana/ops/backup_full_encrypted.sh
```

### 5-0. 安全確認（導入前に1分）

```bash
sudo head -n 80 /var/www/singkana/ops/backup_full_encrypted.sh
sudo grep -nE "gpg|AES256|BACKUP_GPG_PASSPHRASE|--batch|loopback|passphrase-fd|sha256|manifest" \
  /var/www/singkana/ops/backup_full_encrypted.sh
command -v gpg && gpg --version | head -n 2
```

### 5-1. パスフレーズを EnvironmentFile で管理（推奨）

`BACKUP_GPG_PASSPHRASE=...` をコマンドラインに直接書かず、root のみ読めるファイルで管理します。

```bash
sudo install -d -m 700 /etc/singkana
sudo tee /etc/singkana/backup.env >/dev/null <<'EOF'
BACKUP_GPG_PASSPHRASE=YOUR_STRONG_PASS
EOF
sudo chmod 600 /etc/singkana/backup.env
sudo chown root:root /etc/singkana/backup.env
```

### 5-2. systemd service/timer を配置

```bash
sudo cp /var/www/singkana/ops/singkana-backup-encrypted.service /etc/systemd/system/
sudo cp /var/www/singkana/ops/singkana-backup-encrypted.timer   /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now singkana-backup-encrypted.timer
```

### 5-3. 即時テスト

```bash
# 手動で1回実行
sudo systemctl start singkana-backup-encrypted.service

# 結果確認
systemctl list-timers --all | grep singkana-backup-encrypted
sudo journalctl -u singkana-backup-encrypted.service --no-pager -n 80
sudo ls -lh /var/backups/singkana | tail -n 20
```

### 5-4. 直接実行（必要時のみ）

```bash
# 対話式（gpgがパスフレーズを聞く）
sudo /var/www/singkana/ops/backup_full_encrypted.sh
```

### 生成物

- `<backup_dir>/singkana_FULL_YYYYmmdd-HHMMSS.tgz.gpg`
- `<backup_dir>/singkana_FULL_YYYYmmdd-HHMMSS.tgz.gpg.sha256`
- `<backup_dir>/singkana_FULL_YYYYmmdd-HHMMSS.manifest.txt`

デフォルトでは平文の `.tgz` は削除されます（`--keep-plain` 指定時のみ保持）。
また、デフォルトで 14 日より古いバックアップを自動削除します（`--retention-days 0` で無効化可能）。
