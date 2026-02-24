#!/usr/bin/env python3
"""
SingKANA "no traces" audit

目的:
- B案（サーバ処理は残すが“保存しない/ログしない”）が守れているかを機械検査する。
- 検査ログ自体が漏えい源にならないように、needle平文や一致本文は出力しない。

出力:
- docs/no-traces-report.md（人間向け）
- artifacts/no-traces-report.json（機械向け）

注意:
- これは“適法化”ではなく、痕跡/事故率を下げるための監査ツール。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import random
import string
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


NEEDLE_PREFIX = "SINGKANA_AUDIT_NEEDLE"


def utc_now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_needle(ts_iso: str) -> str:
    # 例: SINGKANA_AUDIT_NEEDLE_20260224T160500Z_A7K3M9
    ts_compact = ts_iso.replace("-", "").replace(":", "").replace("Z", "Z").replace("T", "T")
    rand = "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(6))
    return f"{NEEDLE_PREFIX}_{ts_compact}_{rand}"


def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Finding:
    category: str
    path: str
    matches: int
    first_offsets: list[int]
    bytes_scanned: int


@dataclass(frozen=True)
class ScanSkip:
    category: str
    path: str
    reason: str


def iter_files(root: Path, *, exclude_dirs: set[str]) -> Iterable[Path]:
    # os.walk で枝刈り（Windowsで .git 等の列挙が重くなるのを避ける）
    for dirpath, dirnames, filenames in os.walk(str(root)):
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        for fn in filenames:
            yield Path(dirpath) / fn


def scan_file_for_needle(
    p: Path,
    needle_bytes: bytes,
    *,
    max_bytes: int,
    max_offsets: int,
) -> tuple[int, list[int], int]:
    """
    returns: (match_count, offsets[], bytes_scanned)
    - 本文は返さない
    - offset はファイル先頭からの byte offset
    """
    size = p.stat().st_size
    if size > max_bytes:
        raise ValueError(f"file_too_large:{size}")

    n = len(needle_bytes)
    if n <= 0:
        return 0, [], 0

    found = 0
    offsets: list[int] = []
    scanned = 0
    overlap = b""
    pos = 0

    with p.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)  # 1MB
            if not chunk:
                break
            buf = overlap + chunk
            start = 0
            while True:
                idx = buf.find(needle_bytes, start)
                if idx < 0:
                    break
                found += 1
                off = pos - len(overlap) + idx
                if len(offsets) < max_offsets:
                    offsets.append(off)
                start = idx + 1
            scanned += len(chunk)
            pos += len(chunk)
            # 次回の境界またぎ対策
            if len(buf) >= (n - 1):
                overlap = buf[-(n - 1) :]
            else:
                overlap = buf

    return found, offsets, scanned


def http_post_json(url: str, origin: str, body: dict) -> tuple[int, str]:
    # 本文はログしない。レスポンス本文も返すが、呼び出し側で保管/出力しないこと。
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Origin": origin},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        status = int(getattr(resp, "status", 200))
        text = resp.read().decode("utf-8", errors="replace")
        return status, text


def safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def write_text(p: Path, s: str) -> None:
    safe_mkdir(p.parent)
    p.write_text(s, encoding="utf-8")


def write_json(p: Path, obj: dict) -> None:
    safe_mkdir(p.parent)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def scan_local(
    repo_dir: Path,
    needle: str,
    *,
    max_bytes: int,
    also_scan_repo_globs: bool,
) -> tuple[list[Finding], list[ScanSkip], dict]:
    needle_b = needle.encode("utf-8")

    findings: list[Finding] = []
    skips: list[ScanSkip] = []

    # --- explicit targets (high signal) ---
    db_path = Path(os.getenv("SINGKANA_DB_PATH", str(repo_dir / "singkana.db")))
    if not db_path.is_absolute():
        db_path = (repo_dir / db_path).resolve()

    explicit: list[tuple[str, Path]] = []
    explicit.append(("db", db_path))
    explicit.append(("db", Path(str(db_path) + "-wal")))
    explicit.append(("db", Path(str(db_path) + "-shm")))
    explicit.append(("logs", repo_dir / "Logs"))
    explicit.append(("feedback", repo_dir / "docs" / "feedback.jsonl"))

    # 一時領域: 全スキャンは重いので “怪しい prefix” のみ
    tmp_root = Path(tempfile.gettempdir())
    tmp_candidates: list[Path] = []
    try:
        for child in tmp_root.iterdir():
            name = child.name.lower()
            if name.startswith("singkana_sheet_") or name.startswith("singkana_"):
                tmp_candidates.append(child)
            elif name.startswith("playwright") or name.startswith("pw-"):
                tmp_candidates.append(child)
            elif "chromium" in name or "chrome" in name:
                tmp_candidates.append(child)
    except Exception:
        pass

    for c in tmp_candidates[:40]:
        explicit.append(("tmp", c))

    exclude_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv"}

    # Expand explicit targets into files
    targets: list[tuple[str, Path]] = []
    for cat, p in explicit:
        if not p.exists():
            continue
        try:
            if p.is_file():
                targets.append((cat, p))
            elif p.is_dir():
                for fp in iter_files(p, exclude_dirs=exclude_dirs):
                    targets.append((cat, fp))
        except Exception:
            continue

    # Optionally scan common repo artifacts (medium signal)
    if also_scan_repo_globs:
        # repo全体の総当たりは重いので、可能性が高いディレクトリだけを見る
        scan_roots: list[Path] = []
        for rel in ("Logs", "docs", "artifacts", "tmp", "temp", "backups", "backup"):
            p = repo_dir / rel
            if p.exists():
                scan_roots.append(p)
        # root直下のログ/DBも拾う
        scan_roots.append(repo_dir)

        exts = {".log", ".jsonl", ".db", ".sqlite", ".sqlite3", ".txt"}
        archive_exts = {".zip", ".tgz", ".gz", ".tar"}
        for root in scan_roots:
            for fp in iter_files(root, exclude_dirs=exclude_dirs):
                suf = fp.suffix.lower()
                if suf in exts:
                    targets.append(("repo", fp))
                elif suf in archive_exts:
                    targets.append(("backup", fp))

    # De-dup
    seen: set[str] = set()
    uniq: list[tuple[str, Path]] = []
    for cat, fp in targets:
        key = str(fp.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        uniq.append((cat, fp))

    for cat, fp in uniq:
        try:
            m, offs, scanned = scan_file_for_needle(fp, needle_b, max_bytes=max_bytes, max_offsets=5)
            if m:
                findings.append(Finding(cat, str(fp), m, offs, scanned))
        except ValueError as e:
            msg = str(e)
            if msg.startswith("file_too_large:"):
                skips.append(ScanSkip(cat, str(fp), msg))
        except Exception as e:
            skips.append(ScanSkip(cat, str(fp), f"scan_error:{type(e).__name__}"))

    stats = {
        "explicit_db_path": str(db_path),
        "tmp_root": str(tmp_root),
        "targets_scanned": len(uniq),
        "findings_files": len(findings),
        "skips_files": len(skips),
    }
    return findings, skips, stats


def scan_server_via_ssh(
    ssh_prefix: str,
    needle: str,
    paths: list[str],
    *,
    max_bytes: int,
) -> tuple[list[Finding], list[ScanSkip], dict]:
    """
    ベストエフォートの“設計上のフック”。
    - リモートに python3 がある前提（無ければ skip）
    - needle平文は出力しない（ただしSSH経由で送ること自体は避けられない）
    """
    findings: list[Finding] = []
    skips: list[ScanSkip] = []

    # Remote python script (prints JSON only, no needle)
    remote = r"""
import json, os, sys
from pathlib import Path

needle = os.environ.get("SINGKANA_NEEDLE","").encode("utf-8")
max_bytes = int(os.environ.get("SINGKANA_MAX_BYTES","50000000"))

def scan_file(p: Path):
    try:
        st = p.stat()
        if st.st_size > max_bytes:
            return {"skip":"file_too_large:%d"%st.st_size}
        n = len(needle)
        if n <= 0:
            return {"matches":0,"offsets":[],"scanned":0}
        found=0
        offs=[]
        overlap=b""
        pos=0
        scanned=0
        with p.open("rb") as f:
            while True:
                chunk=f.read(1024*1024)
                if not chunk:
                    break
                buf=overlap+chunk
                start=0
                while True:
                    idx=buf.find(needle, start)
                    if idx < 0:
                        break
                    found += 1
                    off = pos - len(overlap) + idx
                    if len(offs) < 5:
                        offs.append(off)
                    start = idx + 1
                scanned += len(chunk)
                pos += len(chunk)
                overlap = buf[-(n-1):] if len(buf) >= (n-1) else buf
        return {"matches":found,"offsets":offs,"scanned":scanned}
    except Exception as e:
        return {"skip":"scan_error:%s"%type(e).__name__}

def iter_files(p: Path):
    try:
        if p.is_file():
            yield p
        elif p.is_dir():
            for fp in p.rglob("*"):
                try:
                    if fp.is_file():
                        yield fp
                except Exception:
                    continue
    except Exception:
        return

out = {"files":[]}
for raw in sys.argv[1:]:
    p = Path(raw)
    if not p.exists():
        continue
    for fp in iter_files(p):
        r = scan_file(fp)
        out["files"].append({"path":str(fp), **r})
print(json.dumps(out, ensure_ascii=False))
"""

    cmd = f'{ssh_prefix} python3 -c "{remote.strip().replace(chr(10), ";").replace(chr(13), "")}" ' + " ".join(
        [f'"{p}"' for p in paths]
    )

    try:
        env = os.environ.copy()
        env["SINGKANA_NEEDLE"] = needle
        env["SINGKANA_MAX_BYTES"] = str(max_bytes)
        cp = subprocess.run(cmd, shell=True, check=False, capture_output=True, text=True, env=env, timeout=60)
        if cp.returncode != 0:
            return [], [ScanSkip("server", "<ssh>", f"ssh_failed:exit={cp.returncode}")], {"ssh_exit": cp.returncode}
        data = json.loads(cp.stdout or "{}")
        for f in data.get("files", []):
            path = str(f.get("path") or "")
            if not path:
                continue
            if "skip" in f:
                skips.append(ScanSkip("server", path, str(f.get("skip") or "skip")))
                continue
            m = int(f.get("matches") or 0)
            if m:
                offs = [int(x) for x in (f.get("offsets") or [])][:5]
                scanned = int(f.get("scanned") or 0)
                findings.append(Finding("server", path, m, offs, scanned))
        return findings, skips, {"paths": paths, "ssh_exit": 0}
    except Exception as e:
        return [], [ScanSkip("server", "<ssh>", f"ssh_error:{type(e).__name__}")], {"paths": paths}


def render_md(report: dict) -> str:
    lines: list[str] = []
    lines.append("# SingKANA No-Traces Report")
    lines.append("")
    lines.append(f"- timestamp_utc: `{report['timestamp_utc']}`")
    lines.append(f"- mode: `{report['mode']}`")
    lines.append(f"- needle_sha256_16: `{report['needle_sha256_16']}`")
    lines.append("")
    lines.append("## Result")
    lines.append("")
    lines.append(f"- status: `{report['status']}`")
    lines.append(f"- findings_count: `{report['findings_count']}`")
    lines.append(f"- skipped_count: `{report['skipped_count']}`")
    lines.append("")
    lines.append("## Executed Flows")
    lines.append("")
    flows = report.get("flows") or []
    if not flows:
        lines.append("- (none)")
    else:
        for f in flows:
            name = f.get("name", "")
            ok = "ok" if f.get("ok") else "fail"
            detail = f.get("detail", "")
            if detail:
                lines.append(f"- `{name}`: `{ok}` ({detail})")
            else:
                lines.append(f"- `{name}`: `{ok}`")
    lines.append("")
    lines.append("## Scanned Targets")
    lines.append("")
    st = report.get("scan_stats") or {}
    for k in sorted(st.keys()):
        lines.append(f"- {k}: `{st[k]}`")
    lines.append("")
    lines.append("## Findings (Redacted)")
    lines.append("")
    if not report.get("findings"):
        lines.append("- (none)")
    else:
        for f in report["findings"]:
            offs = ",".join(str(x) for x in (f.get("first_offsets") or []))
            lines.append(f"- `{f.get('category')}` `{f.get('path')}` matches={f.get('matches')} offsets=[{offs}]")
    lines.append("")
    lines.append("## Skipped (Redacted)")
    lines.append("")
    if not report.get("skipped"):
        lines.append("- (none)")
    else:
        for s in report["skipped"][:80]:
            lines.append(f"- `{s.get('category')}` `{s.get('path')}` reason=`{s.get('reason')}`")
        if len(report["skipped"]) > 80:
            lines.append(f"- ... ({len(report['skipped'])-80} more)")
    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- needle 平文と一致本文は出力しない（監査ログが漏えい源にならないため）")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["local", "server"], default="local")
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parent), help="repo root (default: script dir)")
    ap.add_argument("--needle", default="", help="optional: provide a needle (default: auto-generate unique)")
    ap.add_argument("--max-bytes", type=int, default=50_000_000, help="skip files larger than this")
    ap.add_argument("--scan-repo-globs", action="store_true", help="also scan common repo artifacts (*.log/*.jsonl/*.db/archives)")
    ap.add_argument("--base-url", default="", help="optional: exercise APIs (e.g. http://127.0.0.1:8080)")
    ap.add_argument("--origin", default="", help="Origin header for API exercise (defaults to base-url)")
    ap.add_argument("--sheet-token", default="", help="optional: exercise /api/sheet/pdf with token+payload")
    ap.add_argument("--server-ssh", default="", help='server mode: ssh prefix, e.g. "ssh ubuntu@host"')
    ap.add_argument("--server-path", action="append", default=[], help="server mode: path to scan (repeatable)")
    ap.add_argument("--out-md", default=str(Path("docs") / "no-traces-report.md"))
    ap.add_argument("--out-json", default=str(Path("artifacts") / "no-traces-report.json"))
    args = ap.parse_args()

    repo_dir = Path(args.repo).resolve()
    ts = utc_now_iso()
    needle = (args.needle or "").strip() or make_needle(ts)
    needle_sha = sha256_hex(needle)
    needle_sha_16 = needle_sha[:16]

    flows: list[dict] = []

    # --- exercise endpoints (best-effort, without printing payload/response) ---
    base_url = (args.base_url or "").strip().rstrip("/")
    if base_url:
        origin = (args.origin or "").strip() or base_url
        try:
            st, body = http_post_json(f"{base_url}/api/convert", origin, {"text": needle})
            ok = (st == 200)
            # parse only ok flag; do not retain the body
            detail = f"http={st}"
            try:
                j = json.loads(body or "{}")
                ok = ok and bool(j.get("ok"))
            except Exception:
                ok = False
            flows.append({"name": "/api/convert", "ok": ok, "detail": detail})
        except Exception as e:
            flows.append({"name": "/api/convert", "ok": False, "detail": f"error:{type(e).__name__}"})

        if args.sheet_token:
            payload = {
                "sheet_token": str(args.sheet_token),
                "title": "AUDIT",
                "artist": "",
                "lines": [{"orig": needle, "kana": needle}],
            }
            try:
                st, body = http_post_json(f"{base_url}/api/sheet/pdf", origin, payload)
                ok = (st == 200)
                flows.append({"name": "/api/sheet/pdf(token)", "ok": ok, "detail": f"http={st}"})
            except Exception as e:
                flows.append({"name": "/api/sheet/pdf(token)", "ok": False, "detail": f"error:{type(e).__name__}"})
        else:
            flows.append({"name": "/api/sheet/pdf(token)", "ok": False, "detail": "skipped:no_sheet_token"})

    findings: list[Finding] = []
    skips: list[ScanSkip] = []
    scan_stats: dict = {}
    scan_error: str = ""

    # --- scanning (always write report even on error) ---
    try:
        if args.mode == "local":
            findings, skips, stats = scan_local(
                repo_dir,
                needle,
                max_bytes=args.max_bytes,
                also_scan_repo_globs=bool(args.scan_repo_globs),
            )
            scan_stats = {"local": stats}
        else:
            if not args.server_ssh or not args.server_path:
                raise ValueError("server mode requires --server-ssh and at least one --server-path")
            findings, skips, stats = scan_server_via_ssh(
                args.server_ssh, needle, args.server_path, max_bytes=args.max_bytes
            )
            scan_stats = {"server": stats}
    except Exception as e:
        scan_error = f"{type(e).__name__}"
        skips.append(ScanSkip(args.mode, "<scan>", f"scan_failed:{scan_error}"))

    status = "pass" if not findings else "fail"

    report = {
        "timestamp_utc": ts,
        "mode": args.mode,
        "status": status,
        "needle_sha256": needle_sha,
        "needle_sha256_16": needle_sha_16,
        "findings_count": len(findings),
        "skipped_count": len(skips),
        "flows": flows,
        "scan_stats": scan_stats,
        "scan_error": scan_error or None,
        "findings": [
            {
                "category": f.category,
                "path": f.path,
                "matches": f.matches,
                "first_offsets": f.first_offsets,
                "bytes_scanned": f.bytes_scanned,
            }
            for f in findings
        ],
        "skipped": [{"category": s.category, "path": s.path, "reason": s.reason} for s in skips],
    }

    out_md = (repo_dir / args.out_md).resolve()
    out_json = (repo_dir / args.out_json).resolve()
    write_text(out_md, render_md(report))
    write_json(out_json, report)

    # stdout is minimal (no needle, no content)
    print(json.dumps({"status": status, "needle_sha256_16": needle_sha_16, "findings": len(findings)}, ensure_ascii=False))
    return 0 if status == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())

