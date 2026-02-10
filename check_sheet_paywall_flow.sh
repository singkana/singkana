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
SKIP_STEP1=0
EXPECTED_DRAFT_ID=""
PREPARE_FILE=""
STATE_FILE=""

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
info() { echo "ℹ $1"; }

usage() {
  cat <<EOF
Usage: bash check_sheet_paywall_flow.sh [options]

Options:
  --base-url URL       Default: https://singkana.com
  --origin ORIGIN      Default: https://singkana.com
  --session-id ID      Stripe Checkout session id (cs_...)
  --cookie-file PATH   Default: <temp file per run>
  --skip-step1         Skip Step1 and run from claim
  --expected-draft-id  Validate claim draft_id matches expected value
  --prepare PATH       Run Step1, save state JSON, then exit
  --state PATH         Load checkout_id(session_id) from saved state JSON
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
    --skip-step1)
      SKIP_STEP1=1; shift ;;
    --expected-draft-id)
      EXPECTED_DRAFT_ID="${2:-}"; shift 2 ;;
    --prepare)
      PREPARE_FILE="${2:-}"; shift 2 ;;
    --state)
      STATE_FILE="${2:-}"; shift 2 ;;
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

# `--prepare` implies Step1 path.
if [ -n "$PREPARE_FILE" ]; then
  SKIP_STEP1=0
fi

# If session_id is omitted and a state file exists, load checkout_id as session_id.
if [ -z "$SESSION_ID" ] && [ -n "$STATE_FILE" ] && [ -f "$STATE_FILE" ]; then
  STATE_SID=$(python3 - <<PY
import json
p = "$STATE_FILE"
try:
    d = json.load(open(p, encoding="utf-8"))
    print(d.get("checkout_id",""))
except Exception:
    print("")
PY
)
  if echo "$STATE_SID" | grep -q '^cs_'; then
    SESSION_ID="$STATE_SID"
    info "Loaded session_id from state: ${SESSION_ID:0:12}..."
  fi
fi

# When session_id is provided, Step1 should be skipped by default.
if [ -n "$SESSION_ID" ]; then
  SKIP_STEP1=1
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
CHECKOUT_URL=""
CHECKOUT_ID=""
STEP1_DRAFT_ID=""
if [ "$SKIP_STEP1" -eq 0 ]; then
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
  CHECKOUT_ID=$(python3 - <<PY
import json
p = "$BODY"
try:
    data = json.load(open(p, encoding="utf-8"))
    print(data.get("checkout_id",""))
except Exception:
    print("")
PY
  )
  STEP1_DRAFT_ID=$(python3 - <<PY
import json
p = "$BODY"
try:
    data = json.load(open(p, encoding="utf-8"))
    print(data.get("draft_id",""))
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

  # Save state JSON if requested (`--prepare`) or provided (`--state`).
  TARGET_STATE="$PREPARE_FILE"
  if [ -z "$TARGET_STATE" ] && [ -n "$STATE_FILE" ]; then
    TARGET_STATE="$STATE_FILE"
  fi
  if [ -n "$TARGET_STATE" ] && [ -n "$CHECKOUT_ID" ]; then
    python3 - <<PY
import json, time
out = "$TARGET_STATE"
obj = {
  "checkout_id": "$CHECKOUT_ID",
  "checkout_url": "$CHECKOUT_URL",
  "draft_id": "$STEP1_DRAFT_ID",
  "base_url": "$BASE_URL",
  "origin": "$ORIGIN",
  "cookie_file": "$COOKIE_FILE",
  "saved_at": int(time.time()),
}
with open(out, "w", encoding="utf-8") as f:
    json.dump(obj, f, ensure_ascii=False, indent=2)
print(out)
PY
    pass "state saved: $TARGET_STATE"
  fi

  if [ -n "$PREPARE_FILE" ]; then
    info "Prepare mode completed. Open checkout_url, complete payment, then run with --state $PREPARE_FILE"
    echo ""
    echo "=== Summary ==="
    echo -e "${GREEN}PASS:${NC} $PASS_COUNT  ${YELLOW}WARN:${NC} $WARN_COUNT  ${RED}FAIL:${NC} $FAIL_COUNT"
    [ $FAIL_COUNT -eq 0 ] && exit 0 || exit 1
  fi
else
  info "Step1 skipped (session-id provided or --skip-step1)."
fi

if [ -z "$SESSION_ID" ]; then
  if [ "$SKIP_STEP1" -eq 1 ]; then
    fail "session_id is required when Step1 is skipped."
  else
    warn "session_id not provided; stopping after Step1."
    if [ -n "$CHECKOUT_URL" ]; then
      echo "Manual next step: open checkout_url and complete payment."
    fi
  fi
  echo ""
  echo "=== Summary ==="
  echo -e "${GREEN}PASS:${NC} $PASS_COUNT  ${YELLOW}WARN:${NC} $WARN_COUNT  ${RED}FAIL:${NC} $FAIL_COUNT"
  [ $FAIL_COUNT -eq 0 ] && exit 0 || exit 1
fi

# basic guard for obvious placeholder
if ! echo "$SESSION_ID" | grep -q '^cs_'; then
  fail "session_id format is invalid: $SESSION_ID"
  echo "Hint: pass a real Stripe session id (starts with cs_) after payment completion."
  echo ""
  echo "=== Summary ==="
  echo -e "${GREEN}PASS:${NC} $PASS_COUNT  ${YELLOW}WARN:${NC} $WARN_COUNT  ${RED}FAIL:${NC} $FAIL_COUNT"
  exit 1
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
  echo ""
  echo "[Claim response body]"
  cat "$CLAIM"
  echo ""
  echo "=== Summary ==="
  echo -e "${GREEN}PASS:${NC} $PASS_COUNT  ${YELLOW}WARN:${NC} $WARN_COUNT  ${RED}FAIL:${NC} $FAIL_COUNT"
  exit 1
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
CLAIM_DRAFT_ID=$(python3 - <<PY
import json
p = "$CLAIM"
try:
    data = json.load(open(p, encoding="utf-8"))
    print(data.get("draft_id",""))
except Exception:
    print("")
PY
)

if [ -n "$SHEET_TOKEN" ]; then
  pass "sheet_token issued"
else
  fail "sheet_token missing"
  echo ""
  echo "[Claim response body]"
  cat "$CLAIM"
  echo ""
  echo "=== Summary ==="
  echo -e "${GREEN}PASS:${NC} $PASS_COUNT  ${YELLOW}WARN:${NC} $WARN_COUNT  ${RED}FAIL:${NC} $FAIL_COUNT"
  exit 1
fi

if [ -n "$EXPECTED_DRAFT_ID" ]; then
  if [ "$CLAIM_DRAFT_ID" = "$EXPECTED_DRAFT_ID" ]; then
    pass "draft_id matches expected ($EXPECTED_DRAFT_ID)"
  else
    fail "draft_id mismatch: expected=$EXPECTED_DRAFT_ID got=$CLAIM_DRAFT_ID"
  fi
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
