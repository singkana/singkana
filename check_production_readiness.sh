#!/bin/bash
# SingKANA 本番投入前チェックリスト

echo "=== SingKANA 本番投入前チェック ==="
echo ""

# 色定義
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

# チェック関数
check_pass() {
    echo -e "${GREEN}✓${NC} $1"
    ((PASS_COUNT++))
}

check_fail() {
    echo -e "${RED}✗${NC} $1"
    ((FAIL_COUNT++))
}

check_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((WARN_COUNT++))
}

# 1. サービス実行ユーザーの確認（P0-A: systemdの実行ユーザーを取得して権限を照合）
echo "1. サービス実行ユーザーの確認（P0-A）"
SERVICE_USER=$(systemctl show -p User singkana 2>/dev/null | cut -d= -f2)
if [ -z "$SERVICE_USER" ]; then
    # フォールバック: systemctl cat から取得
    SERVICE_USER=$(systemctl cat singkana 2>/dev/null | grep "^User=" | cut -d= -f2)
fi

if [ -z "$SERVICE_USER" ] || [ "$SERVICE_USER" = "" ]; then
    check_fail "サービス実行ユーザーが取得できません（root扱いの可能性。systemd設定を確認）"
    SERVICE_USER="root"  # フォールバック
elif [ "$SERVICE_USER" = "root" ]; then
    check_warn "サービス実行ユーザー: root（非推奨。専用ユーザーを推奨）"
else
    check_pass "サービス実行ユーザー: $SERVICE_USER"
fi
echo ""

# 2. DBディレクトリの権限確認（P0-B: 実際に書き込みテスト）
echo "2. DBディレクトリの権限確認（P0-B）"
DB_DIR="/var/lib/singkana"
if [ -d "$DB_DIR" ]; then
    DIR_OWNER=$(stat -c '%U' "$DB_DIR" 2>/dev/null || stat -f '%Su' "$DB_DIR" 2>/dev/null)
    DIR_PERM=$(stat -c '%a' "$DB_DIR" 2>/dev/null || stat -f '%OLp' "$DB_DIR" 2>/dev/null)
    
    if [ "$DIR_OWNER" = "$SERVICE_USER" ]; then
        check_pass "ディレクトリ所有者: $DIR_OWNER (正しい)"
    else
        check_fail "ディレクトリ所有者: $DIR_OWNER (期待: $SERVICE_USER)"
    fi
    
    if [ "$DIR_PERM" = "755" ] || [ "$DIR_PERM" = "775" ]; then
        check_pass "ディレクトリ権限: $DIR_PERM (OK)"
    else
        check_warn "ディレクトリ権限: $DIR_PERM (推奨: 755)"
    fi
    
    # P0-B: 実際に書き込みテスト（.wal/.shmが作れることを確認）
    TEST_FILE="$DB_DIR/.perm_test_$$"
    if sudo -u "$SERVICE_USER" touch "$TEST_FILE" 2>/dev/null; then
        sudo -u "$SERVICE_USER" rm -f "$TEST_FILE" 2>/dev/null
        check_pass "書き込みテスト: 成功（.wal/.shmファイルが作成可能）"
    else
        check_fail "書き込みテスト: 失敗（サービスユーザーがディレクトリに書き込めません）"
    fi
    
    # SQLiteの実際の読み書きテスト（可能なら）
    if command -v sqlite3 &> /dev/null && [ -f "$DB_DIR/singkana.db" ]; then
        if sudo -u "$SERVICE_USER" sqlite3 "$DB_DIR/singkana.db" "PRAGMA journal_mode;" >/dev/null 2>&1; then
            JOURNAL_MODE=$(sudo -u "$SERVICE_USER" sqlite3 "$DB_DIR/singkana.db" "PRAGMA journal_mode;" 2>/dev/null | head -1)
            if [ "$JOURNAL_MODE" = "wal" ]; then
                check_pass "SQLite WALモード: 有効（推奨）"
            else
                check_warn "SQLite WALモード: $JOURNAL_MODE（WALモード推奨）"
            fi
        fi
    fi
else
    check_fail "DBディレクトリが存在しません: $DB_DIR"
fi
echo ""

# 3. DBファイルの存在確認
echo "3. DBファイルの存在確認"
DB_PATH="${SINGKANA_DB_PATH:-/var/lib/singkana/singkana.db}"
if [ -f "$DB_PATH" ]; then
    DB_SIZE=$(ls -lh "$DB_PATH" | awk '{print $5}')
    check_pass "DBファイル存在: $DB_PATH (サイズ: $DB_SIZE)"
    
    # テーブル確認
    if command -v sqlite3 &> /dev/null; then
        TABLES=$(sqlite3 "$DB_PATH" "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('waitlist', 'waitlist_rate_limit');" 2>/dev/null)
        if echo "$TABLES" | grep -q "waitlist"; then
            check_pass "waitlistテーブル存在"
        else
            check_fail "waitlistテーブルが存在しません"
        fi
    fi
else
    check_warn "DBファイルが存在しません（初回起動時に自動作成されます）"
fi
echo ""

# 4. サービス状態確認
echo "4. サービス状態確認"
if systemctl is-active --quiet singkana; then
    check_pass "サービスは起動中"
else
    check_fail "サービスが停止しています"
fi

if systemctl is-enabled --quiet singkana; then
    check_pass "サービスは自動起動有効"
else
    check_warn "サービスは自動起動無効"
fi
echo ""

# 5. 環境変数確認（P0-D: secrets.envがsystemdに読み込まれているか）
echo "5. 環境変数確認（P0-D）"
if [ -f "/etc/singkana/secrets.env" ]; then
    check_pass "secrets.env存在"
    
    # P0-D: systemdがsecrets.envを読み込んでいるか確認
    ENV_FILE=$(systemctl show singkana 2>/dev/null | grep -i "EnvironmentFile" | head -1)
    if echo "$ENV_FILE" | grep -q "secrets.env"; then
        check_pass "systemdがsecrets.envを読み込み設定済み"
    else
        check_warn "systemdのEnvironmentFileにsecrets.envが設定されていない可能性"
    fi
    
    # 実際にサービスが環境変数を読み込んでいるか（ログから確認）
    if sudo journalctl -u singkana -n 100 --no-pager 2>/dev/null | grep -q "SMTP_ENABLED\|SINGKANA_DB_PATH"; then
        check_pass "環境変数がサービスに読み込まれている（ログから確認）"
    else
        check_warn "環境変数の読み込み確認ができません（ログに記録がない可能性）"
    fi
    
    if grep -q "SINGKANA_DB_PATH" /etc/singkana/secrets.env; then
        check_pass "SINGKANA_DB_PATH設定済み"
    else
        check_warn "SINGKANA_DB_PATH未設定（デフォルト値を使用）"
    fi
    
    if grep -q "SMTP_ENABLED=1" /etc/singkana/secrets.env; then
        if grep -q "SMTP_USER" /etc/singkana/secrets.env && grep -q "SMTP_PASSWORD" /etc/singkana/secrets.env; then
            check_pass "SMTP設定あり"
        else
            check_warn "SMTP_ENABLED=1 だが認証情報が不完全"
        fi
    else
        check_warn "SMTP無効（メール送信はスキップされます）"
    fi
else
    check_fail "secrets.envが存在しません: /etc/singkana/secrets.env"
fi
echo ""

# 6. ログ確認（エラーがないか）
echo "6. 最近のログ確認（エラー）"
RECENT_ERRORS=$(sudo journalctl -u singkana -n 50 --no-pager 2>/dev/null | grep -i "error\|exception\|failed" | tail -5)
if [ -z "$RECENT_ERRORS" ]; then
    check_pass "最近のエラーログなし"
else
    check_warn "最近のエラーログあり（確認推奨）"
    echo "$RECENT_ERRORS" | sed 's/^/  /'
fi
echo ""

# 7. ネットワーク確認（P0-C: /api/waitlist ヘルスチェック）
echo "7. ネットワーク確認（P0-C）"
if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/healthz 2>/dev/null | grep -q "200"; then
    check_pass "ローカルヘルスチェック (/healthz): OK"
else
    check_fail "ローカルヘルスチェック (/healthz): 失敗"
fi

# P0-C: /api/waitlist に対してローカルからヘルスチェック
WAITLIST_RESPONSE=$(curl -s -X POST http://127.0.0.1:5000/api/waitlist \
    -H "Content-Type: application/json" \
    -H "Origin: http://127.0.0.1:5000" \
    -d '{"email":"test@example.com"}' 2>/dev/null)

if [ -n "$WAITLIST_RESPONSE" ]; then
    # JSONが返るか、okがbooleanであるかを確認
    if echo "$WAITLIST_RESPONSE" | grep -q '"ok"'; then
        OK_VALUE=$(echo "$WAITLIST_RESPONSE" | grep -o '"ok":[^,}]*' | cut -d: -f2 | tr -d ' ')
        if [ "$OK_VALUE" = "true" ] || [ "$OK_VALUE" = "false" ]; then
            check_pass "/api/waitlist: JSON応答正常（ok: $OK_VALUE）"
        else
            check_warn "/api/waitlist: JSON応答あり（ok値の形式確認推奨）"
        fi
    else
        check_warn "/api/waitlist: 応答あり（JSON形式の確認推奨）"
    fi
else
    check_fail "/api/waitlist: 応答なし（サービスが正常に動作していない可能性）"
fi
echo ""

# 8. ファイル権限確認（重要ファイル）
echo "8. 重要ファイルの権限確認"
if [ -f "/var/www/singkana/app_web.py" ]; then
    FILE_OWNER=$(stat -c '%U' /var/www/singkana/app_web.py 2>/dev/null || stat -f '%Su' /var/www/singkana/app_web.py 2>/dev/null)
    if [ "$FILE_OWNER" = "deploy" ] || [ "$FILE_OWNER" = "root" ]; then
        check_pass "app_web.py所有者: $FILE_OWNER (OK)"
    else
        check_warn "app_web.py所有者: $FILE_OWNER (推奨: deploy)"
    fi
fi
echo ""

# 結果サマリー
echo "=== チェック結果サマリー ==="
echo -e "${GREEN}✓ 合格: $PASS_COUNT${NC}"
echo -e "${YELLOW}⚠ 警告: $WARN_COUNT${NC}"
echo -e "${RED}✗ 失敗: $FAIL_COUNT${NC}"
echo ""

if [ $FAIL_COUNT -eq 0 ]; then
    if [ $WARN_COUNT -eq 0 ]; then
        echo -e "${GREEN}🎉 すべてのチェックをパスしました。本番投入可能です。${NC}"
        exit 0
    else
        echo -e "${YELLOW}⚠ 警告がありますが、本番投入は可能です。${NC}"
        exit 0
    fi
else
    echo -e "${RED}✗ 失敗項目があります。修正してから本番投入してください。${NC}"
    exit 1
fi
