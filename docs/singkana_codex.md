# SingKANA Codex Handoff (sanitized)

目的:
- Codex/Cursor に SingKANA の現状を引き継ぎ、壊さずに改善を進めるための単一ファイル。
- secrets の実値は禁止。変数名一覧のみ。

禁止:
- /etc/singkana/secrets.env の値を出力/記録/共有しない
- git push / reset --hard / 本番破壊操作を自動実行しない

生成元:
- snapshot: C:\temp\singkana_snapshot_20260303-104232
- generated_at: 2026-03-03 10:57:00

---
## Systemd unit (sanitized)

```
# /etc/systemd/system/singkana.service
[Unit]
Description=SingKANA Gunicorn Service
After=network.target

[Service]
User=www-data
Group=www-data
WorkingDirectory=/var/www/singkana
EnvironmentFile=/etc/singkana/secrets.env
ExecStart=/var/www/singkana/venv/bin/gunicorn --bind 127.0.0.1:5000 --workers 2 app_web:app
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target

# /etc/systemd/system/singkana.service.d/10-logdir.conf
[Service]
Environment=<REDACTED>

# /etc/systemd/system/singkana.service.d/20-playwright.conf
[Service]
Environment=<REDACTED>

# /etc/systemd/system/singkana.service.d/30-sheetpdf.conf
[Service]
Environment=<REDACTED>

# /etc/systemd/system/singkana.service.d/35-gunicorn-timeout.conf
[Service]
ExecStart=
ExecStart=/var/www/singkana/venv/bin/gunicorn --bind 127.0.0.1:5000 --workers 2 --timeout 60 app_web:app
```

---
## Systemd show (key properties)

```
ExecStart={ path=/var/www/singkana/venv/bin/gunicorn ; argv[]=/var/www/singkana/venv/bin/gunicorn --bind 127.0.0.1:5000 --workers 2 --timeout 60 app_web:app ; ignore_errors=no ; start_time=[Sun 2026-03-01 01:29:24 JST] ; stop_time=[n/a] ; pid=1018463 ; code=(null) ; status=0/0 }
WorkingDirectory=/var/www/singkana
User=www-data
Group=www-data
FragmentPath=/etc/systemd/system/singkana.service
DropInPaths=/etc/systemd/system/singkana.service.d/10-logdir.conf /etc/systemd/system/singkana.service.d/20-playwright.conf /etc/systemd/system/singkana.service.d/30-sheetpdf.conf /etc/systemd/system/singkana.service.d/35-gunicorn-timeout.conf
```

---
## Env var names only (NO VALUES)

```
APP_BASE_URL
BILLING_DB_PATH
COOKIE_SECURE
OPENAI_API_KEY
SINGKANA_ADMIN_TOKEN
SINGKANA_ALLOW_EXTERNAL_LLM
SINGKANA_DB_PATH
SINGKANA_DEV_PRO
SINGKANA_DEV_PRO_ALLOW_IPS
SINGKANA_DEV_PRO_TOKEN
SINGKANA_FEEDBACK_STORE_MODE
SINGKANA_FEEDBACK_WEBHOOK
SINGKANA_FILE_LOG
SINGKANA_INTERNAL_ALLOW_UIDS
SINGKANA_INTERNAL_ENABLE_KEY
SINGKANA_INTERNAL_HMAC_SECRET
SINGKANA_INTERNAL_SIG_MAX_AGE_DAYS
SINGKANA_SHEET_TOKEN_SECRET
SINGKANA_UID_TRACE
SINGKANA_UID_TRACE_PATHS
SINGKANA_UID_TRACE_RAW_UA
SINGKANA_UID_TRACE_TARGET_UIDS
SMTP_ENABLED
SMTP_FROM
SMTP_HOST
SMTP_PASSWORD
SMTP_PORT
SMTP_USER
STRIPE_CANCEL_URL
STRIPE_PRICE_PRO_MONTHLY
STRIPE_PRICE_PRO_YEARLY
STRIPE_PUBLISHABLE_KEY
STRIPE_SECRET_KEY
STRIPE_SUCCESS_URL
STRIPE_WEBHOOK_SECRET
```

---
## Repo snapshot (git status/head/log/diff)

```
PWD: /var/www/singkana
LS:
total 17964
drwxrwxr-x 33 deploy deploy   20480 Mar  1 01:29 .
drwxr-xr-x  5 root   root      4096 Dec 16 20:46 ..
-rw-rw-r--  1 deploy deploy       0 Jan 13 18:32 2
drwxr-xr-x  5 deploy deploy    4096 Feb  3 18:01 airpaws-ios
-rw-r--r--  1 deploy deploy    2932 Dec  9 23:04 analyze_feedback.py
-rw-r--r--  1 deploy deploy      81 Dec  9 22:26 analyze_feedback.py.bak.20251209-222649
-rw-r--r--  1 root   root    150172 Mar  1 01:29 app_web.py
-rw-r--r--  1 deploy deploy    3274 Jan  3 22:37 app_web.py.add_assets_route.2026-01-03_223742.bak
-rw-r--r--  1 deploy deploy   30766 Jan  3 12:44 app_web.py.add_static_paywall.2026-01-03_135948.bak
-rw-r--r--  1 deploy deploy    3143 Jan  3 14:31 app_web.py.after_hardreset_preclean.2026-01-03_145927.bak
-rw-r--r--  1 deploy deploy   55766 Jan 24 00:29 app_web.py.bak
-rw-r--r--  1 deploy deploy    5537 Dec  3 18:35 app_web.py.bak_20251203_183526
-rw-r--r--  1 deploy deploy    5537 Dec  3 23:36 app_web.py.bak_20251203_233615
-rw-r--r--  1 deploy deploy    5537 Dec  4 00:42 app_web.py.bak_20251204_004230
-rw-r--r--  1 deploy deploy    3301 Dec  4 00:45 app_web.py.bak_20251204_004514
-rw-r--r--  1 deploy deploy    3301 Dec  4 01:20 app_web.py.bak_20251204_012024
-rw-r--r--  1 deploy deploy    3301 Dec  4 01:40 app_web.py.bak_20251204_014011
-rw-r--r--  1 deploy deploy   13780 Dec  9 23:56 app_web.py.bak.20251209-235607
-rw-r--r--  1 deploy deploy   15842 Dec 11 00:17 app_web.py.bak.20251214-223525
-rw-r--r--  1 deploy deploy    7359 Dec 14 23:48 app_web.py.bak.20251214-235022
-rw-r--r--  1 deploy deploy    7359 Dec 15 00:03 app_web.py.bak.20251215-001648
-rw-r--r--  1 deploy deploy   11144 Dec 15 19:50 app_web.py.bak.20251215-201001
-rw-r--r--  1 deploy deploy   11144 Dec 15 19:50 app_web.py.bak.20251216-000437.before_admin_ui
-rw-r--r--  1 deploy deploy   14449 Dec 16 00:04 app_web.py.bak.20251216-153540
-rw-r--r--  1 deploy deploy   14449 Dec 16 00:04 app_web.py.bak.20251216-154646
-rw-r--r--  1 deploy deploy   14449 Dec 16 16:20 app_web.py.bak.20251216-162038
-rw-r--r--  1 deploy deploy   16596 Dec 17 00:15 app_web.py.bak.2025-12-24_231547
-rw-r--r--  1 deploy deploy   23838 Dec 24 23:19 app_web.py.bak.20251225-004515
-rw-r--r--  1 deploy deploy   23986 Dec 25 00:45 app_web.py.bak.20251225_005810
-rw-r--r--  1 deploy deploy   23914 Dec 25 00:58 app_web.py.bak.20251226_223104
-rw-r--r--  1 deploy deploy   24344 Dec 26 22:31 app_web.py.bak.20251226_223433
-rw-r--r--  1 deploy deploy   24761 Dec 26 22:34 app_web.py.bak.20251226_223602
-rw-r--r--  1 deploy deploy   23046 Dec 26 22:36 app_web.py.bak.20251226_223707
-rw-r--r--  1 deploy deploy   23046 Dec 26 22:37 app_web.py.bak.20251226_224401
-rw-r--r--  1 deploy deploy   23295 Dec 26 22:44 app_web.py.bak.20251226_224855
-rw-r--r--  1 deploy deploy   23401 Dec 27 22:25 app_web.py.bak.20251227_234151
-rw-r--r--  1 deploy deploy   23869 Dec 27 23:42 app_web.py.bak.2025-12-28_222801
-rw-r--r--  1 deploy deploy   24839 Dec 30 14:46 app_web.py.bak.2025-12-30_145452
-rw-r--r--  1 deploy deploy   24670 Dec 30 14:54 app_web.py.bak.2025-12-30_151235
-rw-r--r--  1 deploy deploy   24708 Dec 30 15:33 app_web.py.bak.2025-12-30_160440
-rw-r--r--  1 deploy deploy    3406 Jan  3 22:37 app_web.py.bak.2026-01-05_235532
-rw-r--r--  1 deploy deploy    6747 Jan  7 15:20 app_web.py.bak.2026-01-07_161028
-rw-r--r--  1 deploy deploy    6747 Jan  7 15:20 app_web.py.bak.2026-01-07_162241
-rw-r--r--  1 deploy deploy  112371 Feb 17 00:10 app_web.py.bak.20260217_011545
-rw-r--r--  1 deploy deploy  104576 Feb 17 12:48 app_web.py.bak.20260217_125210
-rw-r--r--  1 deploy deploy  114091 Feb 17 12:52 app_web.py.bak.20260217_170720
-rw-r--r--  1 deploy deploy    5190 Jan  3 15:57 app_web.py.bak_before_canonical_2026-01-03_155710
-rw-r--r--  1 deploy deploy    3405 Jan  3 15:59 app_web.py.bak_before_canonical_2026-01-03_155940
-rw-r--r--  1 deploy deploy    6940 Jan  5 23:55 app_web.py.bak.before_stripe_2026-01-06_001547
-rw-r--r--  1 deploy deploy      36 Jan  6 00:58 app_web.py.bak.before_stripe_apply_2026-01-06_005916
-rw-r--r--  1 deploy deploy    5327 Jan  6 00:59 app_web.py.bak.before_stripe_apply_2026-01-06_010534
-rw-r--r--  1 deploy deploy    3406 Jan  6 01:07 app_web.py.bak.billing_restore.2026-01-07_151957
-rw-r--r--  1 deploy deploy  104576 Feb 17 12:33 app_web.py.bak.fix_feedback_20260217_123331
-rw-r--r--  1 deploy deploy  106632 Feb 17 12:36 app_web.py.bak.fix_feedback2_20260217_123630
-rw-r--r--  1 deploy deploy    8134 Jan  7 16:22 app_web.py.bak.fix_price_keys.2026-01-07_173911
-rw-r--r--  1 deploy deploy    8134 Jan  7 16:22 app_web.py.bak.pricefix.2026-01-07_201518
-rw-r--r--  1 deploy deploy    9382 Jan  7 22:59 app_web.py.bak.prostore.2026-01-08_231527
-rw-r--r--  1 deploy deploy  123740 Feb 23 16:47 app_web.py.bak.uidtrace.20260223-164732
-rw-r--r--  1 deploy deploy   25292 Jan  2 15:18 app_web.py.before_reformat.2026-01-02_155717.bak
-rw-r--r--  1 deploy deploy   24559 Jan  2 00:24 app_web.py.billing_reformat.2026-01-02_105733.bak
-rw-r--r--  1 deploy deploy   24559 Jan  2 00:24 app_web.py.billing_reformat.2026-01-02_112202.bak
-rw-r--r--  1 deploy deploy   23178 Jan  2 11:22 app_web.py.billing_reformat.2026-01-02_112213.bak
-rw-r--r--  1 deploy deploy   25292 Jan  2 15:18 app_web.py.billing_swap.2026-01-02_160724.bak
-rw-rw-r--  1 deploy deploy      64 Jan 13 18:32 app_web.py.broken_2026-01-03_160539
-rw-rw-r--  1 deploy deploy    5327 Jan 13 18:32 app_web.py.broken.2026-01-06_010705
-rw-rw-r--  1 deploy deploy   15704 Jan 13 18:32 app_web.py.broken.2026-01-12_225405
-rw-r--r--  1 deploy deploy   30766 Jan  3 12:28 app_web.py.clean_paste.2026-01-03_124439.bak
-rw-r--r--  1 deploy deploy  422302 Jan  2 16:07 app_web.py.dedupe.2026-01-02_162559.bak
-rw-r--r--  1 deploy deploy  422302 Jan  2 16:07 app_web.py.dedupe2.2026-01-02_164139.bak
-rw-r--r--  1 deploy deploy   25290 Jan  1 19:54 app_web.py.dedup_helpers.2026-01-01_221849.bak
-rw-r--r--  1 deploy deploy   24698 Dec 30 15:31 app_web.py.fix.2025-12-30_153322.bak
-rw-r--r--  1 deploy deploy   30986 Jan  3 13:59 app_web.py.fix_paywall_route.2026-01-03_141415.bak
-rw-r--r--  1 deploy deploy   28436 Jan  2 19:48 app_web.py.gate_convert.2026-01-03_120709.bak
-rw-r--r--  1 deploy deploy   29999 Jan  3 12:07 app_web.py.gate_convert_fix.2026-01-03_121414.bak
-rw-r--r--  1 deploy deploy   23876 Jan  1 22:18 app_web.py.helpers_add.2026-01-02_002450.bak
-rw-r--r--  1 deploy deploy   24559 Jan  2 00:24 app_web.py.helpers_add.2026-01-02_002641.bak
-rw-r--r--  1 deploy deploy   25136 Dec 30 18:33 app_web.py.invfailfix.2025-12-30_215348.bak
-rw-r--r--  1 deploy deploy   24760 Dec 30 16:04 app_web.py.isprocfix.2025-12-30_164718.bak
-rw-r--r--  1 deploy deploy   24760 Dec 30 16:47 app_web.py.isprocfix2.2025-12-30_170514.bak
-rw-r--r--  1 deploy deploy   14449 Dec 16 00:04 app_web.py.lock.v1.9.0-feedback-stable
-rw-r--r--  1 deploy deploy      77 Dec 16 00:10 app_web.py.lock.v1.9.0-feedback-stable.sha256
-rw-r--r--  1 deploy deploy   25458 Dec 31 05:08 app_web.py.paidlinefix.2025-12-31_114903.bak
-rw-r--r--  1 deploy deploy   31167 Jan  3 14:22 app_web.py.paywallroute_hardreset.2026-01-03_143129.bak
-rw-r--r--  1 deploy deploy   31170 Jan  3 14:14 app_web.py.paywallroute_repair.2026-01-03_142251.bak
-rw-r--r--  1 deploy deploy   30986 Jan  3 13:59 app_web.py.preclean.2026-01-03_141324.bak
-rw-r--r--  1 deploy deploy  106757 Feb 17 12:36 app_web.py.pre_restore_20260217_124752
-rw-r--r--  1 deploy deploy   50003 Jan 21 00:53 app_web.py.redacted
-rw-r--r--  1 deploy deploy   29902 Jan  3 12:14 app_web.py.relocate_gate.2026-01-03_122841.bak
-rw-r--r--  1 deploy deploy    3143 Jan  3 14:31 app_web.py.restore_convert.2026-01-03_151051.bak
-rw-r--r--  1 deploy deploy   25593 Dec 30 21:53 app_web.py.rmdbg.2025-12-31_004111.bak
-rw-r--r--  1 deploy deploy   28678 Jan  2 19:43 app_web.py.rm_dup_status.2026-01-02_194858.bak
-rw-r--r--  1 deploy deploy   25458 Dec 31 00:41 app_web.py.safepaid.2025-12-31_011646.bak
-rw-r--r--  1 deploy deploy   25458 Dec 31 01:16 app_web.py.safepaid2.2025-12-31_050857.bak
-rw-r--r--  1 deploy deploy   28336 Jan  2 19:43 app_web.py.status_rewrite.2026-01-02_194323.bak
-rw-r--r--  1 deploy deploy   23510 Jan  2 16:41 app_web.py.trim_tail.2026-01-02_164709.bak
-rw-r--r--  1 deploy deploy   25412 Dec 31 11:49 app_web.py.webhookfmt.2026-01-01_195425.bak
-rw-r--r--  1 deploy deploy   24583 Jan  1 19:54 app_web.py.webhookfmt.2026-01-01_195444.bak
-rw-r--r--  1 deploy deploy   23178 Jan  2 11:22 app_web.py.webhook_harden.2026-01-02_141309.bak
-rw-r--r--  1 deploy deploy   23178 Jan  2 11:22 app_web.py.webhook_harden2.2026-01-02_151831.bak
-rw-r--r--  1 deploy deploy   23480 Jan  2 16:47 app_web.py.webhook_hardfinal.2026-01-02_183325.bak
-rw-r--r--  1 deploy deploy   25412 Dec 31 11:49 app_web.py.webhook_replace.2026-01-01_172823.bak
-rw-r--r--  1 deploy deploy   26089 Jan  2 18:33 app_web.py.webhook_rewrite.2026-01-02_194306.bak
drwxr-xr-x  2 deploy deploy    4096 Feb 17 00:17 _archive
drwxr-xr-x  2 root   root      4096 Feb 24 23:35 artifacts
drwxr-xr-x  5 deploy deploy    4096 Feb 24 16:37 assets
drwxr-xr-x  5 deploy deploy    4096 Jan  4 14:44 assets.bak.2026-01-04_144428
drwxr-xr-x  6 deploy deploy    4096 Jan  4 14:45 assets.rollback_before_restore.2026-01-04_151059
-rw-r--r--  1 root   root     19725 Feb 24 23:35 audit_no_traces.py
drwxr-xr-x  5 deploy deploy    4096 Jan 20 22:29 backups
drwxr-xr-x  3 deploy deploy    4096 Jan 11 00:07 _bak
drwxr-xr-x  3 deploy deploy    4096 Feb 10 12:15 .cache
-rw-rw-r--  1 deploy deploy    5887 Jan 14 23:42 CHANGELOG_20260114.md
-rw-rw-r--  1 deploy deploy 1349811 Jan 16 00:03 ChatGPT Image 2026年1月4日 12_38_00 2.png
-rw-r--r--  1 deploy deploy    2150 Jan 16 22:38 check_db.sh
-rw-r--r--  1 deploy deploy   12385 Jan 16 22:38 check_production_readiness.sh
-rw-r--r--  1 root   root     10437 Feb 24 23:35 check_sheet_paywall_flow.sh
-rw-r--r--  1 deploy deploy    4357 Dec  7 23:34 check_stack.py
-rw-rw-r--  1 deploy deploy    3021 Jan 13 21:00 create_favicons.py
-rw-rw-r--  1 deploy deploy     590 Jan 13 18:32 .cursorrules
-rw-r--r--  1 deploy deploy    1480 Jan 16 22:38 DEPLOY.md
drwxrwxr-x  4 deploy deploy    4096 Feb 28 00:00 docs
drwxr-xr-x  2 deploy deploy    4096 Feb 24 23:35 en
-rw-r--r--  1 deploy deploy      29 Dec 16 17:34 .env
-rw-rw-r--  1 deploy deploy       0 Jan 13 18:32 ENV
-rw-r--r--  1 deploy deploy     359 Dec 16 12:24 .env.bak.20251216-125750
-rw-r--r--  1 deploy deploy     359 Dec 16 12:57 .env.bak.20251216-132031
-rw-r--r--  1 deploy deploy    1016 Jan  4 13:27 favicon.svg
drwxr-xr-x  8 deploy deploy    4096 Mar  1 01:29 .git
-rw-r--r--  1 root   root       436 Feb 28 00:00 .gitattributes
-rw-r--r--  1 root   root       371 Feb 24 23:35 .gitignore
drwxr-xr-x  2 deploy deploy    4096 Feb 25 00:52 guide
-rw-rw-r--  1 deploy deploy   15260 Jan 16 00:03 IMPLEMENTATION_SUMMARY_20260114.md
-rw-r--r--  1 deploy deploy   13258 Feb 18 00:04 index_backup_20251204_213613.html
-rw-r--r--  1 deploy deploy   13258 Feb 18 00:04 index_backup_20251204_213716.html
-rw-r--r--  1 deploy deploy   10106 Jan 17 22:06 index_en_final.html
-rw-r--r--  1 deploy deploy    9544 Jan 17 22:06 index_en_updated.html
-rw-r--r--  1 root   root    241749 Mar  1 01:29 index.html
-rw-r--r--  1 deploy deploy   57700 Jan 10 23:34 index.html.20260110_233402.bak
-rw-r--r--  1 deploy deploy   54498 Jan  4 13:59 index.html.add_tuner.2026-01-04_140019.bak
-rw-r--r--  1 deploy deploy  199931 Feb 17 12:58 index.html.bak.
-rw-r--r--  1 deploy deploy   16529 Dec  4 00:42 index.html.bak_20251204_004230
-rw-r--r--  1 deploy deploy   11971 Dec  4 01:20 index.html.bak_20251204_012024
-rw-r--r--  1 deploy deploy   11971 Dec  4 01:34 index.html.bak_20251204_013452
-rw-r--r--  1 deploy deploy   13695 Dec  4 01:40 index.html.bak_20251204_014011
-rw-r--r--  1 deploy deploy   13695 Dec  4 21:21 index.html.bak_20251204_212152
-rw-r--r--  1 deploy deploy   30196 Dec 14 21:41 index.html.bak.20251214-215728
-rw-r--r--  1 deploy deploy   47566 Dec 16 00:56 index.html.bak.20251217-231039
-rw-r--r--  1 deploy deploy   47566 Dec 16 00:56 index.html.bak.20251217-232445
-rw-r--r--  1 deploy deploy   47566 Dec 16 00:56 index.html.bak.20251217-232627
-rw-r--r--  1 deploy deploy   47566 Dec 16 00:56 index.html.bak.20251217-232751
-rw-r--r--  1 deploy deploy   48631 Dec 17 23:27 index.html.bak.20251217-234153
-rw-r--r--  1 deploy deploy   48631 Dec 17 23:27 index.html.bak.20251217-234249
-rw-r--r--  1 deploy deploy   49194 Dec 17 23:42 index.html.bak.20251217-234654
-rw-r--r--  1 deploy deploy   49863 Dec 17 23:46 index.html.bak.20251217-235016
-rw-r--r--  1 deploy deploy   49863 Dec 17 23:46 index.html.bak.20251217-235125
-rw-r--r--  1 deploy deploy   50178 Dec 17 23:51 index.html.bak.20251217-235255
-rw-r--r--  1 deploy deploy   50325 Dec 17 23:52 index.html.bak.20251217-235417
-rw-r--r--  1 deploy deploy   50741 Dec 17 23:54 index.html.bak.20251217-235859
-rw-r--r--  1 deploy deploy   50741 Dec 17 23:54 index.html.bak.20251218-000014
-rw-r--r--  1 deploy deploy   54825 Jan  4 14:44 index.html.bak.2026-01-04_144428
-rw-r--r--  1 deploy deploy   65257 Jan 11 23:30 index.html.bak.20260112_000231
-rw-r--r--  1 deploy deploy   65274 Jan 12 01:00 index.html.bak.20260112-203749
-rw-r--r--  1 deploy deploy   65274 Jan 12 01:00 index.html.bak.20260112-204727
-rw-r--r--  1 deploy deploy  146441 Jan 20 23:48 index.html.bak.2026-01-21-005343
-rw-r--r--  1 deploy deploy  191122 Feb 17 01:06 index.html.bak.20260217_010956
-rw-r--r--  1 deploy deploy  191122 Feb 17 01:12 index.html.bak.20260217_011206
-rw-r--r--  1 deploy deploy  191122 Feb 17 01:12 index.html.bak.20260217_012019
-rw-r--r--  1 deploy deploy  191122 Feb 17 01:32 index.html.bak.20260217_013218
-rw-r--r--  1 deploy deploy  191875 Feb 17 01:32 index.html.bak.20260217_122944
-rw-r--r--  1 deploy deploy  201328 Feb 17 13:05 index.html.bak.20260217_130736
-rw-r--r--  1 deploy deploy  201328 Feb 17 13:05 index.html.bak.20260217_132038
-rw-r--r--  1 deploy deploy  201401 Feb 17 13:20 index.html.bak.20260217_132652
-rw-r--r--  1 deploy deploy  201924 Feb 17 13:26 index.html.bak.20260217_133720
-rw-r--r--  1 deploy deploy  202065 Feb 17 13:37 index.html.bak.20260217_140140
-rw-r--r--  1 deploy deploy  201949 Feb 17 14:01 index.html.bak.20260217_170720
-rw-r--r--  1 deploy deploy  221311 Feb 23 14:53 index.html.bak.20260223-145343
-rw-r--r--  1 deploy deploy  131813 Jan 20 18:11 index.html.bak.checkoutfix_2026-01-20-181403
-rw-r--r--  1 deploy deploy  131813 Jan 20 18:11 index.html.bak.checkoutfix_2026-01-20-181649
-rw-r--r--  1 deploy deploy  132993 Jan 20 21:31 index.html.bak.portalfix_2026-01-20-213427
-rw-r--r--  1 deploy deploy  199820 Feb 17 12:58 index.html.bak.price_label_20260217_125827
-rw-r--r--  1 deploy deploy  132521 Jan 20 18:16 index.html.bak.probadge_2026-01-20-212420
-rw-r--r--  1 deploy deploy  131754 Jan 20 16:44 index.html.bak.prostart_2026-01-20-181037
-rw-r--r--  1 deploy deploy   47421 Dec 14 21:57 index.html.bak_theme
-rw-r--r--  1 deploy deploy   52122 Dec 23 21:10 index.html.before_paywall.2026-01-03_134628.bak
-rw-r--r--  1 deploy deploy   55985 Jan  4 01:52 index.html.bodyclassfix.2026-01-04_015238.bak
-rw-r--r--  1 deploy deploy   55985 Jan  4 01:53 index.html.cachebust.2026-01-04_015301.bak
-rw-r--r--  1 deploy deploy   56446 Jan  4 01:05 index.html.cachebust_all.2026-01-04_010506.bak
-rw-r--r--  1 deploy deploy   55985 Jan  4 12:30 index.html.cachebust_all.2026-01-04_123026.bak
-rw-r--r--  1 deploy deploy   55985 Jan  4 01:28 index.html.cachebust_css_only.2026-01-04_012859.bak
-rw-r--r--  1 deploy deploy   54356 Jan  4 13:27 index.html.favicon.2026-01-04_132744.bak
-rw-r--r--  1 deploy deploy   54652 Jan  4 14:40 index.html.icon.2026-01-04_144008.bak
-rw-r--r--  1 deploy deploy   52122 Dec 23 21:10 index.html.inject_paywall.2026-01-03_134639.bak
-rw-r--r--  1 deploy deploy   54572 Jan  4 14:00 index.html.kdt.2026-01-04_144001.bak
-rw-r--r--  1 deploy deploy   55844 Jan  4 00:34 index.html.lightfix_FINAL_2026-01-04_003420.bak
-rw-r--r--  1 deploy deploy   52163 Jan  3 13:46 index.html.paywall_cachebust.2026-01-03_181547.bak
-rw-r--r--  1 deploy deploy   52122 Dec 23 21:10 index.html.pricing_patch.2026-01-05_220628.bak
-rw-r--r--  1 deploy deploy   56466 Jan  4 01:13 index.html.remove_darkfixed.2026-01-04_011334.bak
-rw-r--r--  1 deploy deploy   54015 Jan  3 23:58 index.html.studio_classpatch.2026-01-03_235848.bak
-rw-r--r--  1 deploy deploy   54336 Jan  4 00:15 index.html.studio_force_test.2026-01-04_001525.bak
-rw-r--r--  1 deploy deploy   52183 Jan  3 23:58 index.html.studio_lightfix.2026-01-03_235839.bak
-rw-r--r--  1 deploy deploy   53920 Jan  4 00:25 index.html.studio_lightfix_kdesign.2026-01-04_002526.bak
-rw-r--r--  1 deploy deploy   54316 Jan  3 23:58 index.html.theme_cachebust.2026-01-03_235857.bak
-rw-r--r--  1 deploy deploy   54336 Jan  3 23:59 index.html.theme_cachebust.2026-01-03_235938.bak
-rw-r--r--  1 deploy deploy   54420 Jan  4 13:27 index.html.tuner.2026-01-04_134634.bak
drwxr-xr-x  2 deploy deploy    4096 Nov 30 23:54 log
drwxr-xr-x  2 deploy deploy    4096 Dec  5 00:14 logs
drwxr-xr-x  2 deploy deploy    4096 Feb 15 23:14 Logs
drwxr-xr-x  2 deploy deploy    4096 Feb 18 00:04 lp
drwxr-xr-x  2 deploy deploy    4096 Dec  9 15:43 lp_backup
drwxr-xr-x 75 deploy deploy    4096 Feb 17 00:05 node_modules
-rw-r--r--  1 deploy deploy 4931374 Feb  3 18:01 ogp.png
drwxr-xr-x  2 deploy deploy    4096 Mar  1 01:29 ops
-rw-r--r--  1 deploy deploy     337 Feb 18 00:04 package.json
-rw-r--r--  1 deploy deploy   41282 Feb 18 00:04 package-lock.json
-rw-r--r--  1 deploy deploy    3842 Jan  3 17:32 paywall_gate.js
-rw-r--r--  1 deploy deploy    3508 Jan  3 13:59 paywall_gate.js.bak.2026-01-03_165416
-rw-r--r--  1 deploy deploy    3585 Jan  3 13:46 paywall_gate.js.broken.2026-01-03_135934.bak
-rw-r--r--  1 deploy deploy    4654 Jan  3 17:18 paywall_gate.js.broken.2026-01-03_173206.bak
-rw-r--r--  1 deploy deploy    3508 Jan  3 13:59 paywall_gate.js.preclean.2026-01-03_141324.bak
-rw-r--r--  1 deploy deploy    3762 Jan  3 16:54 paywall_gate.js.ui_gate.2026-01-03_171800.bak
-rw-r--r--  1 deploy deploy      83 Feb 18 00:04 postcss.config.js
-rw-r--r--  1 deploy deploy    9959 Feb 18 00:04 privacy.html
-rw-r--r--  1 deploy deploy    1967 Dec  4 01:20 privacy.html.bak_20251204_012024
-rw-r--r--  1 deploy deploy    1967 Dec  4 01:40 privacy.html.bak_20251204_014011
-rw-r--r--  1 deploy deploy    1967 Dec  4 21:32 privacy.html.bak_20251204_213225
-rw-r--r--  1 root   root      4108 Feb 24 23:35 purge_sensitive_data.py
drwxr-xr-x  2 deploy deploy    4096 Feb 24 00:16 __pycache__
-rw-r--r--  1 deploy deploy      68 Dec  5 23:51 README.md
-rw-r--r--  1 deploy deploy     223 Feb 18 00:04 requirements.txt
drwxr-xr-x  2 deploy deploy    4096 Feb 24 23:35 romaji
drwxrwxr-x  2 deploy deploy    4096 Feb 25 00:52 .sca
drwxr-xr-x 10 deploy deploy    4096 Feb  3 18:01 sca-os
-rw-r--r--  1 deploy deploy    1934 Nov 26 08:05 setup_singkana_example.sh
-rw-r--r--  1 deploy deploy   11163 Dec  9 19:19 singkana_core.js
-rw-r--r--  1 deploy deploy   11163 Dec  9 19:19 singkana_core.js.bak.20251223-222913
-rw-rw-r--  1 deploy deploy       0 Jan 13 18:32 singkana_core.js.save
-rw-rw-r--  1 deploy deploy   12230 Jan 13 18:32 singkana_core_v0.9.0_open_beta.zip
-rw-r--r--  1 deploy deploy    8870 Dec  6 01:03 singkana_core_v1.0_backup.js
-rw-r--r--  1 deploy deploy   81920 Feb 10 12:05 singkana.db
-rw-rw-r--  1 deploy deploy    3716 Jan 13 18:32 singkana_diag.sh
-rw-r--r--  1 root   root     26636 Feb 24 23:35 singkana_engine.py
-rw-r--r--  1 deploy deploy    5013 Dec  3 12:39 singkana_engine.py.bak_20251203_123952
-rw-r--r--  1 deploy deploy    1559 Dec  3 12:52 singkana_engine.py.bak_20251203_125223
-rw-r--r--  1 deploy deploy    1534 Dec  3 13:46 singkana_engine.py.bak_20251203_134654
-rw-r--r--  1 deploy deploy    4005 Dec  3 14:01 singkana_engine.py.bak_20251203-140124
-rw-r--r--  1 deploy deploy    2311 Dec  3 14:21 singkana_engine.py.bak_20251203_142104
-rw-r--r--  1 deploy deploy    2989 Dec  3 14:32 singkana_engine.py.bak_20251203_143220
-rw-r--r--  1 deploy deploy    2467 Dec  3 15:34 singkana_engine.py.bak_20251203_153401
-rw-r--r--  1 deploy deploy    2450 Dec  3 15:49 singkana_engine.py.bak_20251203_154903
-rw-r--r--  1 deploy deploy    3010 Dec  3 16:03 singkana_engine.py.bak_20251203_160341
-rw-r--r--  1 deploy deploy    3181 Dec  3 19:53 singkana_engine.py.bak_20251203_195337
-rw-r--r--  1 deploy deploy    3181 Dec  3 20:40 singkana_engine.py.bak_20251203_204011
-rw-r--r--  1 deploy deploy    6541 Dec  3 21:34 singkana_engine.py.bak_20251203_213421
-rw-r--r--  1 deploy deploy    6541 Dec  3 21:34 singkana_engine.py.bak_20251203_213439
-rw-r--r--  1 deploy deploy    5015 Dec  3 21:51 singkana_engine.py.bak_20251203_215124
-rw-r--r--  1 deploy deploy    5015 Dec  3 22:16 singkana_engine.py.bak_20251203_221638
-rw-r--r--  1 deploy deploy   12062 Dec  3 23:58 singkana_engine.py.bak_20251203_235821
-rw-r--r--  1 deploy deploy   12224 Dec  4 00:14 singkana_engine.py.bak_20251204_001438
-rw-rw-r--  1 deploy deploy 1349811 Jan 16 00:03 singkana_favicon_image.png
-rw-r--r--  1 root   root      3030 Feb 27 00:42 singkana_sheet.html
-rw-rw-r--  1 deploy deploy   27923 Jan 13 18:32 singkana_submit_sanitized_20251213.zip
drwxr-xr-x  3 deploy deploy    4096 Jan  4 17:03 snapshots
drwxr-xr-x  3 deploy deploy    4096 Feb  3 18:01 static
-rw-r--r--  1 deploy deploy   10750 Feb  3 18:01 style.css
drwxr-xr-x  3 deploy deploy    4096 Feb 23 14:58 submit_singkana_sanitized
drwxr-xr-x  3 deploy deploy    4096 Feb 23 14:58 submit_singkana_v1
-rw-r--r--  1 deploy deploy     955 Feb 18 00:04 tailwind.config.js
-rw-r--r--  1 deploy deploy    9815 Feb 18 00:04 terms.html
-rw-r--r--  1 deploy deploy    2581 Dec  4 01:20 terms.html.bak_20251204_012024
-rw-r--r--  1 deploy deploy    2581 Dec  4 01:40 terms.html.bak_20251204_014011
-rw-r--r--  1 deploy deploy    2581 Dec  4 21:31 terms.html.bak_20251204_213140
-rw-r--r--  1 deploy deploy   53690 Feb  3 18:01 tmp_singkana_inline.js
-rw-rw-r--  1 deploy deploy    5251 Feb 24 15:27 tokusho.html
-rw-rw-r--  1 deploy deploy     192 Jan 13 18:32 udo systemctl edit singkana.service
drwxr-xr-x  4 deploy deploy    4096 Feb 10 12:07 ugc-factory
drwxr-xr-x  6 deploy deploy    4096 Feb 15 00:49 venv
-rw-rw-r--  1 deploy deploy     265 Feb 24 15:01 vercel.json
-rw-r--r--  1 deploy deploy      63 Dec 16 17:20 VERSION
drwxrwxr-x  2 deploy deploy    4096 Jan 13 18:32 .vscode
-rw-rw-r--  1 deploy deploy   25673 Jan 13 18:32 whitepaper_backup_20251209-154337.zip

GIT REMOTE:
origin	git@github.com:singkana/singkana.git (fetch)
origin	git@github.com:singkana/singkana.git (push)

GIT STATUS:
## main...origin/main

GIT HEAD:
ef975b8

GIT LOG:
ef975b8 (HEAD -> main, origin/main) P0: requested_mode authoritative, mode_applied/mode_reason response
01191ed Fix smoke script: correct encoding and grep escape patterns
555c972 Force LF for extensionless smoke script via .gitattributes
8836b97 Add symbol set spec and version-control smoke script
76a1ff0 Stabilize kana override keys using lineNo instead of array index
f0c37f6 Add per-line kana edit mode with symbol toolbar
c9d5c5b Normalize kana variants in Studio display and PDF payload
19b8f91 Normalize PDF symbol variants to match Studio display
ceeab31 Normalize PDF breath markers to dot and align legend
6c8e155 fix(pdf): use launch_persistent_context for temp profile
4e8b3c1 Improve studio UX: separate blocks and replace overwrite confirm with modal
feede11 fix(copy): avoid DEV PRO ON literal in public source
3cd7f12 fix(copy): remove dev badge text from public HTML
a7e4056 Merge pull request #3 from singkana/harden-lyrics-no-traces-20260224
0d6fb3a (origin/harden-lyrics-no-traces-20260224) add no-traces audit tooling and ignore generated audit reports
8e98125 harden lyric handling: avoid persistence/logging and tighten sheet flow
73173f0 fix(legal): use Issei Takada in tokusho
02a5537 feat(legal): add EN policy pages
daf7331 fix(romaji): translate footer links to English
c10b343 chore(vercel): redirect romaji tool to VPS

DIFF STAT:

DIFF NAMES:

SENSITIVE FILES (tracked name scan):

.gitignore:
.venv/
venv/
__pycache__/
*.pyc

logs/
log/
backups/
snapshots/
_bak/
*_bak/
*.bak
*.bak.*
index_backup_*.html
assets.bak.*/
assets.rollback_*/
_archive/
backup_full.ps1
billing.db
singkana.db

.env
*.env
node_modules/
.cache/
Logs/
static/ugc/*.png
app_web.py.pre_restore_*

# no-traces audit generated reports
/docs/no-traces-report.md
/artifacts/no-traces-report.json

env-like files existence (untracked too, names only):
./.env.bak.20251216-125750
./.env
./.env.bak.20251216-132031
./ugc-factory/.env.example
```

---
## Nginx test

```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```

---
## Journal warnings (tail)

```
Feb 27 06:17:06 vm-3a3b5314-67 systemd[1]: singkana.service: State 'final-sigterm' timed out. Killing.
Feb 27 06:18:36 vm-3a3b5314-67 systemd[1]: singkana.service: Failed with result 'timeout'.
```

---
## Versions

```
Python 3.12.3
pip 24.0 from /usr/lib/python3/dist-packages/pip (python 3.12)
git version 2.43.0
nginx version: nginx/1.24.0 (Ubuntu)
v18.19.1
9.2.0
```
