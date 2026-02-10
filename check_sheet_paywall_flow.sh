#!/usr/bin/env bash
# SingKANA Sheet Paywall E2E check (MVP)
#
# Usage:
#   bash check_sheet_paywall_flow.sh
#   bash check_sheet_paywall_flow.sh --session-id cs_test_xxx
#   bash check_sheet_paywall_flow.sh --base-url https://singkana.com --origin https://singkana.com --session-id cs_live_xxx
#
# Notes:
# - session_id is optional.
# - Without session_id, script validates only "Free -> 402 + checkout_url".
# - With session_id, script continues "claim -> token -> pdf -> token reuse reject".

set -u

BASE_URL="https://singkana.com"
ORIGIN="https://singkana.com"
SESSION_ID=""
COOKIE_FILE=""
WORK_DIR="/tmp/singkana_sheet_check_$$"
PAYLOAD_JSON='{"title":"TEST","artist":"TEST","lines":[{"orig":"Hello","kana":"˘チェケラ～(アウト)"}]}'

mkdir -p "$WORK_DIR"
trap 'rm -rf "$WORK_DIR"' EXIT

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'
PASS_COUNT=0
FAIL_COUNT=0
WARN_COUNT=0

pass() { echo -e "${GREEN}✓${NC} $1"; PASS_COUNT=$((PASS_COUNT+1)); }
fail() { echo -e "${RED}✗${NC} $1"; FAIL_COUNT=$((FAIL_COUNT+1)); }
warn() { echo -e "${YELLOW}⚠${NC} $1"; WARN_COUNT=$((WARN_COUNT+1)); }

usage() {
  cat <<EOF
Usage: bash check_sheet_paywall_flow.sh [options]

Options:
  --base-url URL       Default: https://singkana.com
  --origin ORIGIN      Default: https://singkana.com
  --session-id ID      Stripe Checkout session id (cs_...)
  --cookie-file PATH   Default: <temp file per run>
  --help               Show this help
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --base-url)
      BASE_URL="${2:-}"; shift 2 ;;
    --origin)
      ORIGIN="${2:-}"; shift 2 ;;
    --session-id)
      SESSION_ID="${2:-}"; shift 2 ;;
    --cookie-file)
      COOKIE_FILE="${2:-}"; shift 2 ;;
    --help|-h)
      usage; exit 0 ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 2 ;;
  esac
done

if [ -z "${COOKIE_FILE:-}" ]; then
  COOKIE_FILE="$WORK_DIR/cookies.txt"
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "curl is required."
  exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required."
  exit 2
fi

HDR="$WORK_DIR/hdr.txt"
BODY="$WORK_DIR/body.json"
PDF="$WORK_DIR/sheet.pdf"
CLAIM="$WORK_DIR/claim.json"

echo "=== SingKANA Sheet Paywall Check ==="
echo "BASE_URL: $BASE_URL"
echo "ORIGIN  : $ORIGIN"
echo ""

# Step 1: Free payload -> 402 + checkout_url
HTTP_CODE=$(curl -sS -c "$COOKIE_FILE" -b "$COOKIE_FILE" \
  -D "$HDR" -o "$BODY" \
  -H "Origin: $ORIGIN" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD_JSON" \
  -w "%{http_code}" \
  "$BASE_URL/api/sheet/pdf")

CT=$(grep -i '^Content-Type:' "$HDR" | head -1 | tr -d '\r')
STEP1_ELIGIBLE_PDF=0
CHECKOUT_URL=$(python3 - <<PY
import json,sys
p = "$BODY"
try:
    data = json.load(open(p, encoding="utf-8"))
    print(data.get("checkout_url",""))
except Exception:
    print("")
PY
)

if [ "$HTTP_CODE" = "402" ]; then
  pass "Free payload returns 402 Payment Required"
  if [ -n "$CHECKOUT_URL" ]; then
    pass "checkout_url is present in 402 response"
  else
    warn "checkout_url missing in 402 response"
  fi
elif [ "$HTTP_CODE" = "200" ] && echo "$CT" | grep -qi 'application/pdf'; then
  STEP1_ELIGIBLE_PDF=1
  pass "Step1 returned 200 PDF (already eligible: Pro or existing valid state)"
  warn "Paywall(402) was not hit. Use a fresh cookie/user if you need strict gate verification."
else
  fail "Unexpected Step1 response: http=$HTTP_CODE content-type=${CT:-missing}"
fi

echo ""
echo "[Step1 response header]"
sed -n '1,20p' "$HDR"
echo ""
if [ "$STEP1_ELIGIBLE_PDF" = "1" ]; then
  echo "[Step1 output file]"
  cp "$BODY" "$PDF"
  ls -lh "$PDF" 2>/dev/null || true
  file "$PDF" 2>/dev/null || true
else
  echo "[Step1 response body]"
  cat "$BODY"
fi
echo ""

if [ -z "$SESSION_ID" ]; then
  warn "session_id not provided; stopping after Step1."
  if [ -n "$CHECKOUT_URL" ]; then
    echo "Manual next step: open checkout_url and complete payment."
  fi
  echo ""
  echo "=== Summary ==="
  echo -e "${GREEN}PASS:${NC} $PASS_COUNT  ${YELLOW}WARN:${NC} $WARN_COUNT  ${RED}FAIL:${NC} $FAIL_COUNT"
  [ $FAIL_COUNT -eq 0 ] && exit 0 || exit 1
fi

# Step 2: claim -> token
HTTP_CODE=$(curl -sS -c "$COOKIE_FILE" -b "$COOKIE_FILE" \
  -D "$HDR" -o "$CLAIM" \
  -H "Origin: $ORIGIN" \
  -w "%{http_code}" \
  "$BASE_URL/api/sheet/claim?session_id=$SESSION_ID")

if [ "$HTTP_CODE" = "200" ]; then
  pass "claim endpoint returns 200"
else
  fail "claim expected 200, got $HTTP_CODE"
fi

SHEET_TOKEN=$(python3 - <<PY
import json
p = "$CLAIM"
try:
    data = json.load(open(p, encoding="utf-8"))
    print(data.get("sheet_token",""))
except Exception:
    print("")
PY
)

if [ -n "$SHEET_TOKEN" ]; then
  pass "sheet_token issued"
else
  fail "sheet_token missing"
fi

echo ""
echo "[Claim response body]"
cat "$CLAIM"
echo ""

# Step 3: token pdf -> 200 and PDF
TOKEN_PAYLOAD=$(python3 - <<PY
import json
print(json.dumps({"sheet_token":"$SHEET_TOKEN"}))
PY
)

HTTP_CODE=$(curl -sS -c "$COOKIE_FILE" -b "$COOKIE_FILE" \
  -D "$HDR" -o "$PDF" \
  -H "Origin: $ORIGIN" \
  -H "Content-Type: application/json" \
  -d "$TOKEN_PAYLOAD" \
  -w "%{http_code}" \
  "$BASE_URL/api/sheet/pdf")

if [ "$HTTP_CODE" = "200" ]; then
  pass "token-based PDF returns 200"
else
  fail "token-based PDF expected 200, got $HTTP_CODE"
fi

CT=$(grep -i '^Content-Type:' "$HDR" | head -1 | tr -d '\r')
if echo "$CT" | grep -qi 'application/pdf'; then
  pass "Content-Type is application/pdf"
else
  fail "Expected PDF content type, got: ${CT:-missing}"
fi

if file "$PDF" | grep -qi 'PDF document'; then
  pass "output file is a PDF document"
else
  fail "output file is not a PDF document"
fi

echo ""
echo "[PDF response header]"
sed -n '1,20p' "$HDR"
echo ""
ls -lh "$PDF" 2>/dev/null || true
file "$PDF" 2>/dev/null || true
echo ""

# Step 4: token reuse should fail
HTTP_CODE=$(curl -sS -c "$COOKIE_FILE" -b "$COOKIE_FILE" \
  -D "$HDR" -o "$BODY" \
  -H "Origin: $ORIGIN" \
  -H "Content-Type: application/json" \
  -d "$TOKEN_PAYLOAD" \
  -w "%{http_code}" \
  "$BASE_URL/api/sheet/pdf")

if [ "$HTTP_CODE" = "409" ]; then
  pass "token reuse rejected with 409"
elif [ "$HTTP_CODE" = "401" ] || [ "$HTTP_CODE" = "403" ] || [ "$HTTP_CODE" = "410" ]; then
  pass "token reuse rejected with $HTTP_CODE"
else
  fail "token reuse expected rejection, got $HTTP_CODE"
fi

echo ""
echo "[Token reuse response body]"
cat "$BODY"
echo ""

echo "=== Summary ==="
echo -e "${GREEN}PASS:${NC} $PASS_COUNT  ${YELLOW}WARN:${NC} $WARN_COUNT  ${RED}FAIL:${NC} $FAIL_COUNT"

if [ $FAIL_COUNT -eq 0 ]; then
  exit 0
else
  exit 1
fi
