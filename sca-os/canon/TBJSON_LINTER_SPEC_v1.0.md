# TB-JSON Linter Spec v1.0 (Canonical Draft)

- 実行: Decision Gate 直前のみ
- 入力: TB-JSON v2.1
- 結果: PASS / WARN / HOLD / BLOCK
- 人間が見るのは Top5 のみ（承認疲れ対策）

Top5:
1) risk.adoption_risk
2) risk.reversibility
3) risk.rollback_ref
4) truth_flags (UNKNOWN/CONFLICT)
5) fhb_gate.attack_surface_change

HOLD/BLOCK時は Rejection Trace を必ず発行。

