#!/usr/bin/env bash
# ================================================================
# SingKANA DB Cleanup — 期限切れレコードの定期掃除
# cron で 1日1回 呼ぶ想定（深夜帯推奨）
#
# 対象テーブル:
#   sheet_drafts        — One-Shot PDF の下書き (TTL 30分)
#   sheet_pdf_tokens    — PDF ダウンロードトークン (TTL 10分)
#   transfer_codes      — 端末移行コード (TTL 10分)
#   waitlist_rate_limit — waitlist レートリミット (TTL 1時間)
#   gpt_kana_cache      — GPT発音補正キャッシュ (TTL 7日)
#   events              — イベント計測ログ (TTL 90日)
#
# Usage:
#   sudo -u www-data /var/www/singkana/ops/cleanup_db.sh
#   (--dry-run で削除せず件数だけ表示)
# ================================================================
set -euo pipefail

DB_PATH="${SINGKANA_DB_PATH:-/var/lib/singkana/singkana.db}"
DRY_RUN=0
VERBOSE=0

for arg in "$@"; do
  case "$arg" in
    --dry-run)  DRY_RUN=1 ;;
    --verbose)  VERBOSE=1 ;;
    -h|--help)
      echo "Usage: $0 [--dry-run] [--verbose]"
      echo "  --dry-run   Show counts without deleting"
      echo "  --verbose   Print per-table counts"
      exit 0
      ;;
  esac
done

if [ ! -f "$DB_PATH" ]; then
  echo "[cleanup] ERROR: DB not found at $DB_PATH" >&2
  exit 1
fi

NOW=$(date +%s)
# waitlist_rate_limit は ISO文字列なので別扱い
ONE_HOUR_AGO=$(date -u -d "@$((NOW - 3600))" +"%Y-%m-%dT%H:%M:%S" 2>/dev/null \
  || date -u -r "$((NOW - 3600))" +"%Y-%m-%dT%H:%M:%S" 2>/dev/null \
  || python3 -c "import datetime as d; print((d.datetime.utcnow()-d.timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%S'))")

log() {
  if [ "$VERBOSE" -eq 1 ]; then
    echo "[cleanup] $*"
  fi
}

total_deleted=0

cleanup_table_ts() {
  local table="$1"
  local col="$2"    # expires_at (unix epoch)
  local threshold="$3"

  local count
  count=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM $table WHERE $col < $threshold;")

  log "$table: $count expired rows (threshold=$threshold)"

  if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] $table: $count rows would be deleted"
  else
    if [ "$count" -gt 0 ]; then
      sqlite3 "$DB_PATH" "DELETE FROM $table WHERE $col < $threshold;"
      log "$table: deleted $count rows"
    fi
  fi
  total_deleted=$((total_deleted + count))
}

cleanup_table_iso() {
  local table="$1"
  local col="$2"
  local threshold="$3"

  local count
  count=$(sqlite3 "$DB_PATH" "SELECT COUNT(*) FROM $table WHERE $col < '$threshold';")

  log "$table: $count expired rows (threshold=$threshold)"

  if [ "$DRY_RUN" -eq 1 ]; then
    echo "[dry-run] $table: $count rows would be deleted"
  else
    if [ "$count" -gt 0 ]; then
      sqlite3 "$DB_PATH" "DELETE FROM $table WHERE $col < '$threshold';"
      log "$table: deleted $count rows"
    fi
  fi
  total_deleted=$((total_deleted + count))
}

# --- 掃除実行 ---
# sheet_drafts: expires_at は unix epoch (int)
# 余裕を持って expires_at < NOW（既に期限切れのもの全部）
cleanup_table_ts "sheet_drafts"      "expires_at" "$NOW"
cleanup_table_ts "sheet_pdf_tokens"  "expires_at" "$NOW"
cleanup_table_ts "transfer_codes"    "expires_at" "$NOW"

# waitlist_rate_limit: created_at は ISO 8601 文字列
cleanup_table_iso "waitlist_rate_limit" "created_at" "$ONE_HOUR_AGO"

# gpt_kana_cache: 7日以上前のキャッシュを削除
SEVEN_DAYS_AGO=$((NOW - 604800))
cleanup_table_ts "gpt_kana_cache" "created_at" "$SEVEN_DAYS_AGO"

# events: 90日以上前のイベントを削除
NINETY_DAYS_AGO=$((NOW - 7776000))
cleanup_table_ts "events" "created_at" "$NINETY_DAYS_AGO"

# --- サマリ ---
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')
if [ "$DRY_RUN" -eq 1 ]; then
  echo "[dry-run] Total: $total_deleted rows would be deleted ($TIMESTAMP)"
else
  echo "[cleanup] Done: $total_deleted rows deleted ($TIMESTAMP)"
fi

# WAL チェックポイント（掃除後にファイルサイズを縮小）
if [ "$DRY_RUN" -eq 0 ] && [ "$total_deleted" -gt 0 ]; then
  sqlite3 "$DB_PATH" "PRAGMA wal_checkpoint(TRUNCATE);" >/dev/null 2>&1 || true
  log "WAL checkpoint done"
fi
