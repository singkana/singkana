#!/bin/bash
# P0/P2 smoke: requested_mode=入力保持, effective_mode=裁定, mode_reason
# VM 上で: bash ops/smoke-convert-mode.sh [PRO_UID] [BASE_URL]

set -euo pipefail
PRO_UID="${1:-sk_01KJ040NFR6BQKD1BHMHWA626J}"
BASE="${2:-http://127.0.0.1:5000}"
FREE_UID="${FREE_UID:-sk_01KF3RSQ5EE7359WMM6EHTEVQX}"
RESP=/tmp/smoke_convert_resp.json

echo "=== SingKANA Convert API Smoke (P0 mode + P2 standard) ==="
echo "Base: $BASE  Pro: $PRO_UID  Free: $FREE_UID"
echo ""

# 1) Free + natural 要求 → requested_mode=natural, effective=basic, reason=plan_locked
echo "--- 1) Free + requested_mode=natural → plan_locked ---"
curl -sS -X POST "$BASE/api/convert" \
  -H "Content-Type: application/json" \
  -H "Origin: https://singkana.com" \
  -b "sk_uid=$FREE_UID" \
  -d '{"text":"I was a ghost","requested_mode":"natural"}' \
  -o "$RESP"
out1=$(python3 -c "import json; j=json.load(open('$RESP')); print({k:j.get(k) for k in ['requested_mode','effective_mode','mode_applied','mode_reason','processing_mode']})")
echo "  $out1"
req1=$(python3 -c "import json; print(json.load(open('$RESP')).get('requested_mode',''))")
eff1=$(python3 -c "import json; print(json.load(open('$RESP')).get('effective_mode',''))")
reason1=$(python3 -c "import json; print(json.load(open('$RESP')).get('mode_reason',''))")
if [[ "$req1" == "natural" && "$eff1" == "basic" && "$reason1" == "plan_locked" ]]; then
  echo "  OK: requested_mode=入力保持, plan_locked"
else
  echo "  NG: requested_mode=$req1 (expected natural), effective=$eff1, reason=$reason1"
  exit 1
fi

# 2) Pro + natural 要求 → ok
echo ""
echo "--- 2) Pro + requested_mode=natural → ok ---"
curl -sS -X POST "$BASE/api/convert" \
  -H "Content-Type: application/json" \
  -H "Origin: https://singkana.com" \
  -b "sk_uid=$PRO_UID" \
  -d '{"text":"I was a ghost","requested_mode":"natural"}' \
  -o "$RESP"
out2=$(python3 -c "import json; j=json.load(open('$RESP')); print({k:j.get(k) for k in ['requested_mode','effective_mode','mode_applied','mode_reason']})")
echo "  $out2"
req2=$(python3 -c "import json; print(json.load(open('$RESP')).get('requested_mode',''))")
eff2=$(python3 -c "import json; print(json.load(open('$RESP')).get('effective_mode',''))")
reason2=$(python3 -c "import json; print(json.load(open('$RESP')).get('mode_reason',''))")
if [[ "$req2" == "natural" && "$eff2" == "natural" && "$reason2" == "ok" ]]; then
  echo "  OK: natural applied"
else
  echo "  WARN: Pro でなければ expected natural/ok にならない"
fi

# 3) P2: lines[].standard 保証
echo ""
echo "--- 3) P2: lines[].standard 保証 ---"
missing=$(python3 -c "import json; j=json.load(open('$RESP')); arr=j.get('result') or []; print(len([i for i,x in enumerate(arr) if not isinstance(x,dict) or 'standard' not in x]))")
empty=$(python3 -c "import json; j=json.load(open('$RESP')); arr=j.get('result') or []; print(len([i for i,x in enumerate(arr) if isinstance(x,dict) and str(x.get('standard','')).strip()=='']))")
total=$(python3 -c "import json; print(len(json.load(open('$RESP')).get('result') or []))")
echo "  total=$total missing_standard=$missing empty_standard=$empty"
if [[ "$missing" == "0" && "$empty" == "0" ]]; then
  echo "  OK: all lines have standard"
else
  echo "  NG: P2 standard 欠落"
  exit 1
fi

echo ""
echo "ALL PASS"
