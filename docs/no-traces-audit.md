# No-Traces Audit (B案)

目的:
- 「保存しない/ログしない/外部送信しない」が崩れていないかを、needle方式で機械検査する
- 検査ログ自体が漏えい源にならないよう、needle平文や一致本文は出力しない

## ローカル（毎リリース前・必須）

最小（高シグナル対象のみ）:
- `python audit_no_traces.py --mode local`

広め（Logs/docs/artifacts/backups 等も含める）:
- `python audit_no_traces.py --mode local --scan-repo-globs`

APIも踏む（ローカルで `app_web.py` を起動している前提）:
- `python audit_no_traces.py --mode local --base-url http://127.0.0.1:8080 --origin http://127.0.0.1:8080 --scan-repo-globs`

One-shot PDF の生成経路まで踏む（有効な `sheet_token` がある場合のみ）:
- `python audit_no_traces.py --mode local --base-url https://singkana.com --origin https://singkana.com --sheet-token "<token>" --scan-repo-globs`

成果物:
- `docs/no-traces-report.md`（人間向け）
- `artifacts/no-traces-report.json`（自動判定向け）

## 本番（反映前/反映直後・準必須 → 最終的に必須）

このリポジトリの `audit_no_traces.py` は、ベストエフォートの SSH モードを持ちます。

例（Linux想定・python3がある場合）:
- `python audit_no_traces.py --mode server --server-ssh "ssh user@host" --server-path /var/www/singkana/singkana.db --server-path /var/log/nginx --max-bytes 50000000`

注意:
- SSHモードは「設計上のフック」です（環境差が大きいため、必要に応じて運用に合わせて拡張してください）

## 安全条件（必須）

- needle平文を標準出力に出さない
- 一致した本文断片を出力しない
- HTTPレスポンス全文を出力しない
- 許可される出力は `needle_hash`, `パス`, `件数`, `オフセット/行番号`, `PASS/FAIL` のみ

