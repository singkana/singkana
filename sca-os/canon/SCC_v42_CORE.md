# SCC v42 CORE (Canonical)

## 0. Purpose (Immutable)
- State更新を「説得ゲーム」から「検証ゲーム」へ移す
- Canonicalは“改変可能”ではなく“改憲手続きが必要”な領域とする
- 採用は TB-JSON + Lint + Gate を必須化（通らない限りState更新禁止）

## 1. Canonical Domains
- canon/: 憲法・仕様・不変宣言
- state/: 現在State（機械可読）
- patches/: 改憲提案（TB-JSON + diff + rollback）
- evidence/: EV-...（根拠）
- tests/: T-...（検証）
- tools/: LinterとGateの実装

## 2. Governance Units (Always-On)
- TG (Truth Gate): 根拠なきVERIFIED禁止、Canonical直通のUNKNOWN/CONFLICT禁止
- FHB: Boundary First / Least Privilege / Explicit State を必須化
- HSP: 重要変更は人間承認を必須化（承認なしはHOLD）
- AAU: 変更差分・回帰点・リスクを短く監査可能な形に圧縮

## 3. Decision Gate
- State更新（Canonical採用）は Decision Gate 直前にのみ実行
- GateはTB-JSON Linter PASS/WARN のみ通過可能
- HOLD/BLOCK は Rejection Trace を発行し、次の行動を明示する

## 4. Anti-Approval-Fatigue
- 人間が読むのは Linter標準レポート（Top5）だけ
- 長文summaryは禁止（説得を削る）

