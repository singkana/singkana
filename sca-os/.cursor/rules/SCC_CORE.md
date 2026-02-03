# SCC CORE (Cursor Rules)

- Canonical State は TB-JSON v2.1 でしか更新しない
- TB-JSON は Linter PASS/WARN 以外では採用不可
- “説得”は禁止。Summaryは短く。根拠/テスト/ロールバックが全て
- UNKNOWN/CONFLICT を含む Canonical 更新は HOLD
- PIIは原則禁止。必要なら CONSENTED_SHORT_TERM + HSP必須
- 人間承認が必要なのに approved_by_human=false は HOLD

