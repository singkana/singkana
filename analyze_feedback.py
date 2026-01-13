#!/usr/bin/env python3
"""
SingKANA feedback analyzer (CLI)

Usage:
  python analyze_feedback.py           # 最新 20 件を表示
  python analyze_feedback.py --all     # すべて表示
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FEEDBACK_PATH = os.path.join(BASE_DIR, "docs", "feedback.jsonl")


@dataclass
class Entry:
    raw: Dict[str, Any]
    ts: Optional[str]
    text: str
    song: str
    engine: str


def parse_ts(ts: Optional[str]) -> Optional[datetime]:
    """ISO文字列(Z付きも含む) → datetime。失敗したら None。"""
    if not ts:
        return None
    try:
        # 2025-12-09T10:32:06.793004Z → +00:00 に置き換え
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def sort_key(e: Entry) -> float:
    """
    ソートキーは「UNIXタイム(float)」に統一。
    tz-aware / naive 混在問題を避ける。
    """
    dt = parse_ts(e.ts)
    return dt.timestamp() if dt else 0.0


def load_entries() -> List[Entry]:
    entries: List[Entry] = []

    if not os.path.exists(FEEDBACK_PATH):
        print(f"[INFO] feedback file not found: {FEEDBACK_PATH}")
        return entries

    with open(FEEDBACK_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                # 壊れた行も “raw” として保管
                obj = {"_raw": line}

            ts = obj.get("ts")
            text = str(obj.get("text", ""))
            meta = obj.get("meta", {}) or {}
            song = str(meta.get("song", ""))
            engine = str(meta.get("engine_version", ""))

            entries.append(Entry(obj, ts, text, song, engine))

    # 新しい順
    entries.sort(key=sort_key, reverse=True)
    return entries


def print_table(entries: List[Entry], limit: Optional[int] = 20) -> None:
    if limit is not None:
        entries = entries[:limit]

    if not entries:
        print("[INFO] no entries.")
        return

    print(f"{'#':>3}  {'ts':19}  {'song':20}  {'engine':14}  text")
    print("-" * 90)

    for idx, e in enumerate(entries, start=1):
        ts = (e.ts or "")[:19]
        song = (e.song or "-")[:20]
        engine = (e.engine or "-")[:14]
        text = e.text.replace("\n", "  ")
        print(f"{idx:>3}  {ts:19}  {song:20}  {engine:14}  {text}")


def main(argv: List[str]) -> int:
    show_all = "--all" in argv
    entries = load_entries()
    limit = None if show_all else 20
    print_table(entries, limit=limit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
