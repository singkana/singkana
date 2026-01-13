#!/usr/bin/env bash
# SingKANA 総合ヘルスチェックコマンド
# /var/www/singkana/singkana_diag.sh などに置いて実行

set -euo pipefail

APP_DIR="/var/www/singkana"
SERVICE_NAME="singkana.service"
VENV_DIR="$APP_DIR/venv"
JS_FILE="$APP_DIR/singkana_core.js"
LOCAL_URL_ROOT="http://127.0.0.1"
LOCAL_URL_JS="$LOCAL_URL_ROOT/singkana_core.js"

C_RESET="\033[0m"
C_RED="\033[31m"
C_GREEN="\033[32m"
C_YELLOW="\033[33m"
C_CYAN="\033[36m"

section () {
  echo -e "\n${C_CYAN}========== $1 ==========${C_RESET}"
}

ok ()    { echo -e "${C_GREEN}[OK]${C_RESET}    $*"; }
warn ()  { echo -e "${C_YELLOW}[WARN]${C_RESET}  $*"; }
fail ()  { echo -e "${C_RED}[FAIL]${C_RESET}  $*"; }

echo -e "${C_CYAN}=== SingKANA diagnostic ===${C_RESET}"
echo "Host: $(hostname)"
echo "Time: $(date)"
echo

# 1. systemd (Gunicorn) 状態
section "1. Gunicorn / systemd status ($SERVICE_NAME)"
if systemctl is-active --quiet "$SERVICE_NAME"; then
  ok "service is active (running)"
else
  fail "service is NOT running"
  echo
  echo "---- 最近のログ (journalctl -u $SERVICE_NAME -n 30) ----"
  journalctl -u "$SERVICE_NAME" -n 30 --no-pager || true
fi

# 2. Python アプリの Syntax チェック
section "2. app_web.py syntax check"
if [ -d "$APP_DIR" ] && [ -f "$APP_DIR/app_web.py" ]; then
  cd "$APP_DIR"
  if [ -d "$VENV_DIR" ]; then
    # venv があれば有効化
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
  else
    warn "venv ($VENV_DIR) が見つからないので、システムの python でチェックします"
  fi

  if python -m py_compile app_web.py 2>/tmp/singkana_py_err.log; then
    ok "app_web.py syntax OK"
  else
    fail "app_web.py syntax ERROR"
    echo "---- python エラー内容 ----"
    cat /tmp/singkana_py_err.log
  fi
else
  fail "app_web.py or $APP_DIR not found"
fi

# 3. Nginx の設定 & プロセス確認
section "3. Nginx config & process"
if nginx -t >/tmp/singkana_nginx_test.log 2>&1; then
  ok "nginx -t OK"
else
  fail "nginx -t FAILED"
  cat /tmp/singkana_nginx_test.log
fi

if systemctl is-active --quiet nginx; then
  ok "nginx service is active (running)"
else
  fail "nginx service is NOT running"
fi

echo
echo "Listening on :80/:443 (ss -ltnp | grep -E ':80|:443'):"
ss -ltnp | grep -E ':80|:443' || warn "no process listening on 80/443?"

# 4. ローカル HTTP アクセス確認
section "4. HTTP check via 127.0.0.1"
echo "→ root:"
if curl -sS -o /dev/null -w "%{http_code}\n" "$LOCAL_URL_ROOT" | grep -q "^200$"; then
  ok "GET / -> 200"
else
  fail "GET / -> 200 以外"
fi

echo
echo "→ singkana_core.js header:"
curl -sSI "$LOCAL_URL_JS" | head -n 10 || fail "curl HEAD $LOCAL_URL_JS failed"

# 5. JS ファイルのローカル版 vs 配信版を比較
section "5. JS file diff (disk vs served)"
if [ -f "$JS_FILE" ]; then
  LOCAL_MD5=$(md5sum "$JS_FILE" | awk '{print $1}')
  REMOTE_MD5=$(curl -sS "$LOCAL_URL_JS" | md5sum | awk '{print $1}' || echo "ERROR")

  echo "Local JS : $JS_FILE"
  echo "  md5 = $LOCAL_MD5"
  echo "Remote JS: $LOCAL_URL_JS"
  echo "  md5 = $REMOTE_MD5"

  if [ "$REMOTE_MD5" = "ERROR" ]; then
    fail "リモート JS を取得できませんでした"
  elif [ "$LOCAL_MD5" = "$REMOTE_MD5" ]; then
    ok "JS on disk == JS served by nginx (キャッシュずれなし)"
  else
    fail "JS on disk と nginx が配信している JS の内容が違います"
  fi

  echo
  echo "---- Local JS first lines ----"
  head -n 5 "$JS_FILE"
  echo
  echo "---- Remote JS first lines ----"
  curl -sS "$LOCAL_URL_JS" | head -n 5
else
  fail "JS file not found: $JS_FILE"
fi

section "Done"
echo "診断完了。上の [FAIL] と [WARN] の行を見れば、どこが怪しいか一目でわかる。"
