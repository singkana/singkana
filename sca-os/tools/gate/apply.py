#!/usr/bin/env python3
import datetime
import hashlib
import json
import sys
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "state" / "registry.json"
APPLIED_DIR = ROOT / "state" / "applied"
APPLIED_INDEX = APPLIED_DIR / "index.jsonl"
BACKUPS_DIR = ROOT / "state" / "backups"
REJECTIONS_DIR = ROOT / "state" / "rejections"
REJECTIONS_INDEX = REJECTIONS_DIR / "index.jsonl"
LINTER = ROOT / "tools" / "tbjson_linter" / "lint.py"


def now_iso():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()


def canonical_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _safe_relpath(p: str) -> Path:
    pp = Path(p)
    if pp.is_absolute():
        raise ValueError("absolute paths are not allowed")
    if any(part in ("..",) for part in pp.parts):
        raise ValueError("path traversal is not allowed")
    return pp


def compute_diff_hash(diff_paths: list[str]) -> str:
    h = hashlib.sha256()
    for rel in diff_paths:
        relp = _safe_relpath(rel)
        absp = (ROOT / relp).resolve()
        if ROOT not in absp.parents and absp != ROOT:
            raise ValueError("diff path escapes repository root")
        if not absp.exists() or not absp.is_file():
            raise FileNotFoundError(str(relp))

        h.update(str(relp).replace("\\", "/").encode("utf-8"))
        h.update(b"\0")
        h.update(absp.read_bytes())
        h.update(b"\0")
    return "sha256:" + h.hexdigest()


def required_refs(tb: dict) -> dict:
    missing_evidence_for = []
    missing_tests_for = []

    for c in tb.get("claims", []):
        claim_id = c.get("claim_id", "UNKNOWN")
        ut = c.get("uncertainty_type")
        ev = c.get("evidence_refs") or []
        ts = c.get("test_refs") or []

        if ut == "VERIFIED" and (not ev) and (not ts):
            missing_evidence_for.append(claim_id)
        if ut == "INFERRED" and (not ts):
            missing_tests_for.append(claim_id)

    rollback_missing = not bool((tb.get("risk") or {}).get("rollback_ref"))

    return {
        "missing_evidence_for_verified": missing_evidence_for,
        "missing_tests_for_inferred": missing_tests_for,
        "rollback_missing": rollback_missing,
    }


def write_rejection_trace(trace: dict):
    REJECTIONS_DIR.mkdir(parents=True, exist_ok=True)
    proposal_id = trace.get("proposal_id") or "UNKNOWN"

    out_path = REJECTIONS_DIR / f"{proposal_id}.json"
    out_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with REJECTIONS_INDEX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(trace, ensure_ascii=False) + "\n")


def reject(tb: dict, *, reason_code: str, severity: str, message: str, lint_report: dict | None = None, exit_code: int = 4):
    trace = {
        "trace_version": "1.1",
        "generated_at": now_iso(),
        "proposal_id": tb.get("proposal_id") or "UNKNOWN",
        "gate": "APPLY",
        "reason_code": reason_code,
        "severity": severity,
        "message": message,
        "violated_principle": ["HumanSovereignty"],
        "retry_allowed": True,
        "next_action": "TB-JSON/台帳/差分を修正し、Lint→Gate→Applyを再実行する（Top5とerrorsのみ確認）。",
        "lint_errors": [e.get("code") for e in (lint_report or {}).get("errors", []) or []],
        "required_refs": required_refs(tb),
        "lint_report": lint_report,
    }

    write_rejection_trace(trace)
    print(json.dumps(trace, ensure_ascii=False, indent=2))
    print(f"\n[Apply] REJECT: {reason_code}", file=sys.stderr)
    sys.exit(exit_code)


def ensure_adopted(reg: dict, proposal_id: str, diff_hash: str) -> dict | None:
    for e in reversed(reg.get("adoptions") or []):
        if e.get("proposal_id") == proposal_id and e.get("diff_hash") == diff_hash:
            return e
    return None


def allowed_base(tb: dict) -> Path:
    st = tb.get("state_target")
    if st == "SAND":
        return (ROOT / "state" / "sand").resolve()
    if st == "Canonical":
        return (ROOT / "canon").resolve()
    raise ValueError(f"unknown state_target: {st}")


def apply_ops(tb: dict, base_dir: Path) -> list[dict]:
    ops = ((tb.get("artifacts") or {}).get("apply_ops")) or []
    if not isinstance(ops, list) or len(ops) == 0:
        raise ValueError("artifacts.apply_ops missing/empty")

    applied = []
    for op in ops:
        if not isinstance(op, dict):
            raise ValueError("apply_ops item must be object")
        if op.get("op") != "WRITE_TEXT":
            raise ValueError(f"unsupported op: {op.get('op')}")
        rel = _safe_relpath(str(op.get("path")))
        target = (ROOT / rel).resolve()

        # 反映先を state_target の base に固定（境界）
        if base_dir not in target.parents and target != base_dir:
            raise ValueError(f"target escapes base_dir: {rel}")

        content = op.get("content")
        if not isinstance(content, str):
            raise ValueError("content must be string")
        overwrite = bool(op.get("overwrite", True))

        applied.append(
            {
                "op": "WRITE_TEXT",
                "path": str(rel).replace("\\", "/"),
                "abs_path": str(target),
                "overwrite": overwrite,
                "content": content,
            }
        )
    return applied


def backup_file(proposal_id: str, rel_path: str, abs_path: Path):
    out = (BACKUPS_DIR / proposal_id / rel_path).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(abs_path.read_bytes())


def main():
    if len(sys.argv) < 2:
        print("Usage: apply.py <tb_json_path>", file=sys.stderr)
        sys.exit(2)

    tb_path = Path(sys.argv[1])
    tb = json.loads(tb_path.read_text(encoding="utf-8"))

    # 0) Lint 強制（Applyでも再確認）
    p = subprocess.run([sys.executable, str(LINTER), str(tb_path)], capture_output=True, text=True)
    lint_raw = p.stdout.strip()
    lint_report = None
    try:
        lint_report = json.loads(lint_raw) if lint_raw else None
    except Exception:
        lint_report = None
    code = p.returncode
    if code != 0:
        reject(tb, reason_code="LINT_FAILED", severity="HOLD" if code == 3 else "BLOCK", message="lint not PASS/WARN", lint_report=lint_report, exit_code=code)

    # 1) diff_hash 検証（採用時と同条件）
    diff_paths = ((tb.get("artifacts") or {}).get("diff_paths")) or []
    if not isinstance(diff_paths, list) or len(diff_paths) == 0:
        reject(tb, reason_code="DIFF_PATHS_MISSING", severity="BLOCK", message="artifacts.diff_paths missing/empty", lint_report=lint_report, exit_code=4)
    computed = compute_diff_hash([str(x) for x in diff_paths])
    claimed = ((tb.get("artifacts") or {}).get("diff_hash")) or ""
    if claimed != computed:
        reject(tb, reason_code="DIFF_HASH_MISMATCH", severity="BLOCK", message=f"diff_hash mismatch: claimed={claimed} computed={computed}", lint_report=lint_report, exit_code=4)

    # 2) 台帳確認（採用済みか）
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    pid = tb.get("proposal_id") or "UNKNOWN"
    adopted = ensure_adopted(reg, pid, computed)
    if not adopted:
        reject(tb, reason_code="NOT_ADOPTED", severity="HOLD", message="proposal_id+diff_hash not found in registry.adoptions (run adopt.py first)", lint_report=lint_report, exit_code=3)

    # 3) Apply ops 実行（境界固定 + backup）
    base = allowed_base(tb)
    base.mkdir(parents=True, exist_ok=True)
    ops = apply_ops(tb, base)

    applied_files = []
    for op in ops:
        rel = op["path"]
        target = Path(op["abs_path"])
        target.parent.mkdir(parents=True, exist_ok=True)

        existed = target.exists()
        if existed:
            backup_file(pid, rel, target)
        else:
            # 何も無ければ空バックアップは作らない
            pass

        if existed and (not op["overwrite"]):
            reject(tb, reason_code="TARGET_EXISTS", severity="HOLD", message=f"target exists and overwrite=false: {rel}", lint_report=lint_report, exit_code=3)

        target.write_text(op["content"], encoding="utf-8")
        applied_files.append({"path": rel, "backed_up": existed})

    # 4) applied log
    APPLIED_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "applied_at": now_iso(),
        "proposal_id": pid,
        "state_target": tb.get("state_target"),
        "diff_hash": computed,
        "apply_ops_count": len(ops),
        "applied_files": applied_files,
    }
    with APPLIED_INDEX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(json.dumps(entry, ensure_ascii=False, indent=2))
    print("\n[Apply] APPLIED: logged in state/applied/index.jsonl")


if __name__ == "__main__":
    main()

