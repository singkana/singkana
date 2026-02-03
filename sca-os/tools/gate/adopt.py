#!/usr/bin/env python3
import datetime
import hashlib
import json
import sys
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
STATE_CANON = ROOT / "state" / "canonical_state.json"
REGISTRY = ROOT / "state" / "registry.json"
REJECTIONS_DIR = ROOT / "state" / "rejections"
REJECTIONS_INDEX = REJECTIONS_DIR / "index.jsonl"
LINTER = ROOT / "tools" / "tbjson_linter" / "lint.py"


def now_iso():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()

def canonical_json(obj) -> str:
    # ハッシュ用：順序・空白を固定
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

def chain_hash(prev_hash: str, entry_without_hash: dict) -> str:
    h = hashlib.sha256()
    h.update(prev_hash.encode("utf-8"))
    h.update(b"\n")
    h.update(canonical_json(entry_without_hash).encode("utf-8"))
    return "sha256:" + h.hexdigest()

def ensure_registry_chain(reg: dict) -> tuple[dict, str, str]:
    """
    既存台帳に鎖が無い/途中までの場合の扱い：
    - 既存行に entry_hash が無ければ legacy=true を付与（境界を明示）
    - 鎖の起点は prev_hash="LEGACY" から開始（genesisを明示）
    戻り値: (更新済みreg, adoptions_prev_hash, rejections_prev_hash)
    """
    changed = False
    reg.setdefault("adoptions", [])
    reg.setdefault("rejections", [])

    def last_hash(arr: list[dict]) -> str | None:
        for e in reversed(arr):
            eh = e.get("entry_hash")
            if isinstance(eh, str) and eh.startswith("sha256:"):
                return eh
        return None

    # legacy付与（鎖が無い過去行にだけ）
    for arr_name in ("adoptions", "rejections"):
        arr = reg.get(arr_name) or []
        for e in arr:
            if "entry_hash" not in e:
                if e.get("legacy") is not True:
                    e["legacy"] = True
                    e["legacy_note"] = "pre-hash-chain era (legacy entry)"
                    changed = True

    if changed:
        # いまの内容で書き戻し（以降の追加がprev_hash取得できるように）
        REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    ad_prev = last_hash(reg["adoptions"]) or "LEGACY"
    rj_prev = last_hash(reg["rejections"]) or "LEGACY"
    return reg, ad_prev, rj_prev

def _safe_relpath(p: str) -> Path:
    pp = Path(p)
    if pp.is_absolute():
        raise ValueError("absolute paths are not allowed")
    if any(part in ("..",) for part in pp.parts):
        raise ValueError("path traversal is not allowed")
    return pp


def compute_diff_hash(diff_paths: list[str]) -> str:
    """
    diff_paths で指されたファイル群（内容）から sha256 を計算する。
    連結時にパス名も含めて曖昧性を排除する。
    """
    h = hashlib.sha256()
    for rel in diff_paths:
        relp = _safe_relpath(rel)
        absp = (ROOT / relp).resolve()
        # 念のため boundary を固定（ROOT配下から出ない）
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


def violated_principles_from_lint(lint_report: dict | None) -> list[str]:
    principles = set()
    if not lint_report:
        return ["TruthBeforeState"]

    for e in lint_report.get("errors", []) or []:
        path = e.get("path", "") or ""
        code = e.get("code", "") or ""
        if path == "truth_rules" or code.startswith("LINT_VERIFIED_") or code.startswith("LINT_INFERRED_") or code.startswith("LINT_CANONICAL_NEEDS_SDH_"):
            principles.add("TruthBeforeState")
        elif path == "fhb_rules" or code.startswith("LINT_FHB_") or code.startswith("LINT_BAD_DATA_") or code.startswith("LINT_BAD_PII_") or code.startswith("LINT_PII_"):
            principles.add("BoundaryFirst")
        elif path == "hsp_rules" or code.startswith("LINT_HSP_"):
            principles.add("HumanSovereignty")
        else:
            principles.add("TruthBeforeState")

    return sorted(principles) if principles else ["TruthBeforeState"]


def write_rejection_trace(trace: dict):
    REJECTIONS_DIR.mkdir(parents=True, exist_ok=True)
    proposal_id = trace.get("proposal_id") or "UNKNOWN"

    out_path = REJECTIONS_DIR / f"{proposal_id}.json"
    out_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    with REJECTIONS_INDEX.open("a", encoding="utf-8") as f:
        f.write(json.dumps(trace, ensure_ascii=False) + "\n")

def reject(tb: dict, *, gate: str, reason_code: str, severity: str, message: str, lint_report: dict | None = None, exit_code: int = 4):
    trace = {
        "trace_version": "1.1",
        "generated_at": now_iso(),
        "proposal_id": tb.get("proposal_id") or "UNKNOWN",
        "gate": gate,
        "reason_code": reason_code,
        "severity": severity,
        "message": message,
        "violated_principle": violated_principles_from_lint(lint_report),
        "retry_allowed": True,
        "next_action": "TB-JSONを修正し、Lint→Gateを再実行する（Top5とerrorsのみ確認）。",
        "lint_errors": [e.get("code") for e in (lint_report or {}).get("errors", []) or []],
        "required_refs": required_refs(tb),
        "lint_report": lint_report,
    }

    # registryにも最低限記録（任意だが追跡に便利）
    try:
        reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
        reg, _ad_prev, rj_prev = ensure_registry_chain(reg)
        reg.setdefault("rejections", [])
        entry = {
            "rejected_at": trace["generated_at"],
            "proposal_id": trace["proposal_id"],
            "gate": gate,
            "reason_code": reason_code,
            "severity": severity,
        }
        entry["prev_hash"] = rj_prev
        entry["entry_hash"] = chain_hash(rj_prev, entry)
        reg["rejections"].append(entry)
        REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception:
        # ここで落ちると「拒否ログが消える」ので、registry記録は失敗しても続行
        pass

    write_rejection_trace(trace)
    print(json.dumps(trace, ensure_ascii=False, indent=2))
    print(f"\n[Gate] REJECT: {gate}/{reason_code}", file=sys.stderr)
    sys.exit(exit_code)


def main():
    if len(sys.argv) < 2:
        print("Usage: adopt.py <tb_json_path>", file=sys.stderr)
        sys.exit(2)

    tb_path = Path(sys.argv[1])
    tb = json.loads(tb_path.read_text(encoding="utf-8"))

    # 1) Lint強制
    p = subprocess.run([sys.executable, str(LINTER), str(tb_path)], capture_output=True, text=True)
    lint_raw = p.stdout.strip()
    lint_report = None
    try:
        lint_report = json.loads(lint_raw) if lint_raw else None
    except Exception:
        lint_report = None
    code = p.returncode
    if code != 0:
        reject(
            tb,
            gate="LINTER",
            reason_code="LINT_FAILED",
            severity="HOLD" if code == 3 else "BLOCK",
            message="lint not PASS/WARN",
            lint_report=lint_report,
            exit_code=code,
        )

    # 1.5) diff_hash 本物化（diff_paths から算出して照合）
    diff_paths = ((tb.get("artifacts") or {}).get("diff_paths")) or []
    if not isinstance(diff_paths, list) or len(diff_paths) == 0:
        reject(
            tb,
            gate="GATE",
            reason_code="DIFF_PATHS_MISSING",
            severity="BLOCK",
            message="artifacts.diff_paths missing/empty",
            lint_report=lint_report,
            exit_code=4,
        )

    try:
        computed = compute_diff_hash([str(x) for x in diff_paths])
    except FileNotFoundError as e:
        reject(
            tb,
            gate="GATE",
            reason_code="DIFF_PATH_NOT_FOUND",
            severity="BLOCK",
            message=f"diff path not found: {e}",
            lint_report=lint_report,
            exit_code=4,
        )
    except Exception as e:
        reject(
            tb,
            gate="GATE",
            reason_code="DIFF_HASH_COMPUTE_FAILED",
            severity="BLOCK",
            message=f"diff hash compute failed: {e}",
            lint_report=lint_report,
            exit_code=4,
        )

    claimed = ((tb.get("artifacts") or {}).get("diff_hash")) or ""
    if claimed != computed:
        reject(
            tb,
            gate="GATE",
            reason_code="DIFF_HASH_MISMATCH",
            severity="BLOCK",
            message=f"diff_hash mismatch: claimed={claimed} computed={computed}",
            lint_report=lint_report,
            exit_code=4,
        )

    # 2) Adopt（最小：registryへ採用ログを残すだけ）
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    reg, ad_prev, _rj_prev = ensure_registry_chain(reg)
    entry = {
        "adopted_at": now_iso(),
        "proposal_id": tb.get("proposal_id"),
        "state_target": tb.get("state_target"),
        "mode": tb.get("mode"),
        "diff_hash": tb.get("artifacts", {}).get("diff_hash"),
        "rollback_ref": tb.get("risk", {}).get("rollback_ref"),
    }
    entry["prev_hash"] = ad_prev
    entry["entry_hash"] = chain_hash(ad_prev, entry)
    reg["adoptions"].append(entry)
    REGISTRY.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(lint_report, ensure_ascii=False, indent=2))
    print("\n[Gate] ADOPTED: logged in state/registry.json")


if __name__ == "__main__":
    main()

