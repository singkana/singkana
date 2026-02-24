#!/usr/bin/env python3
"""
Purge potentially sensitive traces from local SingKANA storage.

目的:
- B案（サーバ処理は残すが“保存しない”）へ移行した後に、
  過去に残ってしまった DB / ログの残骸を手動で掃除するための補助スクリプト。

注意:
- これは“安全宣言”ではなく、残骸を減らすための実務ツール。
- 実行前にバックアップを推奨。
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path


def _count(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    cur = conn.execute(sql, params)
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def main() -> int:
    repo_dir = Path(__file__).resolve().parent
    default_db = os.getenv("SINGKANA_DB_PATH", str(repo_dir / "singkana.db"))

    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=default_db, help="path to singkana.db (default: env SINGKANA_DB_PATH or ./singkana.db)")
    ap.add_argument("--execute", action="store_true", help="actually delete; otherwise dry-run")
    ap.add_argument("--vacuum", action="store_true", help="VACUUM after deletes (slow but reduces residual bytes)")
    ap.add_argument("--purge-events", action="store_true", help="DELETE all rows from events table (analytics reset)")
    ap.add_argument("--delete-feedback-jsonl", action="store_true", help="delete docs/feedback.jsonl (if present)")
    ap.add_argument("--delete-engine-logs", action="store_true", help="delete Logs/convert.log and Logs/feedback.log (if present)")
    args = ap.parse_args()

    db_path = Path(args.db).expanduser()
    if not db_path.is_absolute():
        db_path = (repo_dir / db_path).resolve()

    print(f"DB: {db_path}")
    if not db_path.exists():
        print("DB not found; nothing to do.")
        return 0

    conn = sqlite3.connect(str(db_path))
    try:
        # Tables that historically could contain lyric-derived payloads.
        targets = [
            ("sheet_drafts", "DELETE FROM sheet_drafts"),
            ("gpt_kana_cache", "DELETE FROM gpt_kana_cache"),
        ]

        for table, delete_sql in targets:
            try:
                n = _count(conn, f"SELECT COUNT(*) FROM {table}")
            except sqlite3.OperationalError:
                print(f"- {table}: table missing (skip)")
                continue

            print(f"- {table}: rows={n}")
            if args.execute and n:
                conn.execute(delete_sql)
                conn.commit()
                print(f"  deleted {n}")

        if args.purge_events:
            try:
                n = _count(conn, "SELECT COUNT(*) FROM events")
                print(f"- events: rows={n}")
                if args.execute and n:
                    conn.execute("DELETE FROM events")
                    conn.commit()
                    print(f"  deleted {n}")
            except sqlite3.OperationalError:
                print("- events: table missing (skip)")

        if args.vacuum and args.execute:
            print("- VACUUM: start (may take time)")
            conn.execute("VACUUM")
            print("- VACUUM: done")
    finally:
        conn.close()

    if args.delete_feedback_jsonl:
        p = repo_dir / "docs" / "feedback.jsonl"
        if p.exists():
            if args.execute:
                p.unlink()
                print(f"- deleted {p}")
            else:
                print(f"- would delete {p}")
        else:
            print(f"- {p} not found")

    if args.delete_engine_logs:
        for rel in ("Logs/convert.log", "Logs/feedback.log"):
            p = repo_dir / rel
            if p.exists():
                if args.execute:
                    p.unlink()
                    print(f"- deleted {p}")
                else:
                    print(f"- would delete {p}")
            else:
                print(f"- {p} not found")

    if not args.execute:
        print("\nDry-run only. Re-run with --execute to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

