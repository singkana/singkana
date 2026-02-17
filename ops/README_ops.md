# SingKANA 運用スクリプト (`ops/`)

## ファイル一覧

| ファイル | 用途 |
|----------|------|
| `cleanup_db.sh` | DB の期限切れレコード掃除（1日1回） |
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
