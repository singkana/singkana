## sca-os

Cursor上で「TB-JSON → Lint → Decision Gate（採用台帳）」を最小構成で再現する雛形です。

### クイックスタート（ローカル）

```bash
cd sca-os
pip install -r requirements.txt

# Lint
python tools/tbjson_linter/lint.py patches/TB-20260104-0001.sample.json

# Gate（採用ログ記録）
python tools/gate/adopt.py patches/TB-20260104-0001.sample.json
```

### ポリシー（要点）
- Canonical更新は **TB-JSON v2.1** でのみ提案
- TB-JSON は **Linter PASS/WARN 以外は採用不可**
- Canonicalへ **UNKNOWN/CONFLICT** を通さない（HOLD）
- “説得”より **根拠/テスト/ロールバック** を優先（AAU）

