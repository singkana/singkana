#!/usr/bin/env python3
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = ROOT / "canon" / "TBJSON_v2.1.schema.json"
RULES_PATH = ROOT / "tools" / "tbjson_linter" / "rules.yaml"

SEVERITY_ORDER = ["PASS", "WARN", "HOLD", "BLOCK"]

class _Dot:
    """
    dict/list を tb.x 形式で参照するためのラッパ。
    重要：スカラーはラップせず「生値」を返す（比較が死なないように）。
    """

    __slots__ = ("_v",)

    def __init__(self, value):
        self._v = value

    @staticmethod
    def _wrap(x):
        if isinstance(x, (dict, list)):
            return _Dot(x)
        return x  # scalar -> raw value

    def __getattr__(self, name):
        if isinstance(self._v, dict):
            return _Dot._wrap(self._v.get(name))
        raise AttributeError(name)

    def __getitem__(self, key):
        if isinstance(self._v, (dict, list)):
            return _Dot._wrap(self._v[key])
        raise TypeError("not indexable")

    def get(self, key, default=None):
        if isinstance(self._v, dict):
            return _Dot._wrap(self._v.get(key, default))
        return default

    # ---- safety nets: if a Dot leaks into comparisons, unwrap it ----
    def _raw(self):
        return self._v

    def __repr__(self):
        return f"_Dot({self._v!r})"

    def __str__(self):
        return str(self._v)

    def __bool__(self):
        return bool(self._v)

    def __len__(self):
        if isinstance(self._v, (list, dict, str)):
            return len(self._v)
        return 0

    def __eq__(self, other):
        a = self._v
        b = other._v if isinstance(other, _Dot) else other
        return a == b


def lines(s: str) -> int:
    return s.count("\n") + 1 if s else 0


def chars(s: str) -> int:
    return len(s) if s else 0


def startswith(s: str, prefix: str) -> bool:
    return isinstance(s, str) and s.startswith(prefix)


def unique_claim_ids(tb) -> bool:
    ids = [c.get("claim_id") for c in tb.get("claims", [])]
    return len(ids) == len(set(ids))


def refs_format_ok(tb) -> bool:
    for c in tb.get("claims", []):
        for ev in c.get("evidence_refs", []):
            if not isinstance(ev, str) or not ev.startswith("EV-"):
                return False
        for t in c.get("test_refs", []):
            if not isinstance(t, str) or not t.startswith("T-"):
                return False
    return True


def no_verified_without_evidence(tb) -> bool:
    for c in tb.get("claims", []):
        if c.get("uncertainty_type") == "VERIFIED":
            ev = c.get("evidence_refs", [])
            t = c.get("test_refs", [])
            if (not ev) and (not t):
                return False
    return True


def no_unknown_conflict_in_canonical(tb) -> bool:
    if tb.get("state_target") != "Canonical":
        return True
    for c in tb.get("claims", []):
        if c.get("uncertainty_type") in ("UNKNOWN", "CONFLICT"):
            return False
    return True


def no_inferred_without_test(tb) -> bool:
    for c in tb.get("claims", []):
        if c.get("uncertainty_type") == "INFERRED":
            t = c.get("test_refs", [])
            if not t:
                return False
    return True


def require_paths(tb, required_paths):
    missing = []
    for p in required_paths:
        cur = tb
        for part in p.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                missing.append(p)
                break
    return missing


def eval_check(expr: str, tb: dict) -> bool:
    # 超ミニDSL: tbはdict、補助関数のみ許可
    tb_obj = _Dot(tb)
    env = {
        "tb": tb_obj,
        "len": len,
        "lines": lines,
        "chars": chars,
        "startswith": startswith,
        "true": True,
        "false": False,
        "unique": lambda _ignored=None: unique_claim_ids(tb),
        "unique_claim_ids": lambda: unique_claim_ids(tb),
        "refs_format_ok": lambda: refs_format_ok(tb),
        "no_verified_without_evidence": lambda: no_verified_without_evidence(tb),
        "no_unknown_conflict_in_canonical": lambda: no_unknown_conflict_in_canonical(tb),
        "no_inferred_without_test": lambda: no_inferred_without_test(tb),
    }
    # claims[].claim_id のような表現は rules.yaml 側で unique(...) に吸収済み
    # 安全のため builtins を遮断
    return bool(eval(expr, {"__builtins__": {}}, env))


def push_error(errors, code, severity, path, msg):
    errors.append({"code": code, "severity": severity, "path": path, "msg": msg})


def compute_truth_flags(tb):
    flags = set()
    for c in tb.get("claims", []):
        ut = c.get("uncertainty_type")
        if ut in ("UNKNOWN", "CONFLICT"):
            flags.add(ut)
    return sorted(flags)


def top5(tb):
    truth_flags = compute_truth_flags(tb)
    return [
        {"key": "adoption_risk", "value": tb["risk"]["adoption_risk"]},
        {"key": "reversibility", "value": tb["risk"]["reversibility"]},
        {"key": "rollback_ref", "value": tb["risk"]["rollback_ref"] if tb["risk"]["rollback_ref"] else "MISSING"},
        {"key": "truth_flags", "value": truth_flags},
        {"key": "attack_surface_change", "value": tb["fhb_gate"]["attack_surface_change"]},
    ]


def worst(result_a, result_b):
    return SEVERITY_ORDER[max(SEVERITY_ORDER.index(result_a), SEVERITY_ORDER.index(result_b))]


def lint(tb):
    rules = yaml.safe_load(RULES_PATH.read_text(encoding="utf-8"))

    # 0) JSON Schema validate
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    v = Draft202012Validator(schema)
    schema_errors = sorted(v.iter_errors(tb), key=lambda e: e.path)

    errors = []
    result = "PASS"

    for e in schema_errors:
        push_error(errors, "LINT_SCHEMA", "BLOCK", ".".join([str(x) for x in e.path]), e.message)
        result = worst(result, "BLOCK")

    # 1) required_paths (spec上BLOCK)
    missing = require_paths(tb, rules["required_paths"])
    for p in missing:
        push_error(errors, "LINT_REQUIRED_PATH_MISSING", "BLOCK", p, f"missing required path: {p}")
        result = worst(result, "BLOCK")

    # 2) structural rules
    def run_rule(rule, group_name="rules"):
        nonlocal result
        ok = True
        if rule["id"] == "LINT_DUPLICATE_CLAIM_ID":
            ok = unique_claim_ids(tb)
        elif rule["id"] == "LINT_SUMMARY_TOO_LONG":
            ok = (lines(tb.get("summary", "")) <= 2) and (chars(tb.get("summary", "")) <= 200)
        else:
            ok = eval_check(rule["check"], tb)

        if not ok:
            push_error(errors, rule["id"], rule["severity"], group_name, rule["msg"])
            result = worst(
                result,
                "BLOCK"
                if rule["severity"] == "BLOCK"
                else ("HOLD" if rule["severity"] == "HOLD" else "WARN"),
            )
        return ok

    for r in rules.get("rules", []):
        run_rule(r, "rules")

    # truth rules
    for r in rules.get("truth_rules", []):
        if r["check"] == "no_verified_without_evidence":
            ok = no_verified_without_evidence(tb)
        elif r["check"] == "no_unknown_conflict_in_canonical":
            ok = no_unknown_conflict_in_canonical(tb)
        elif r["check"] == "no_inferred_without_test":
            ok = no_inferred_without_test(tb)
        elif r["check"] == "refs_format_ok":
            ok = refs_format_ok(tb)
        else:
            ok = eval_check(r["check"], tb)

        if not ok:
            push_error(errors, r["id"], r["severity"], "truth_rules", r["msg"])
            result = worst(
                result,
                "BLOCK" if r["severity"] == "BLOCK" else ("HOLD" if r["severity"] == "HOLD" else "WARN"),
            )

    # fhb rules
    for r in rules.get("fhb_rules", []):
        ok = eval_check(r["check"], tb)
        if not ok:
            push_error(errors, r["id"], r["severity"], "fhb_rules", r["msg"])
            result = worst(
                result,
                "BLOCK" if r["severity"] == "BLOCK" else ("HOLD" if r["severity"] == "HOLD" else "WARN"),
            )

    # hsp rules
    for r in rules.get("hsp_rules", []):
        ok = eval_check(r["check"], tb)
        if not ok:
            push_error(errors, r["id"], r["severity"], "hsp_rules", r["msg"])
            result = worst(
                result,
                "BLOCK" if r["severity"] == "BLOCK" else ("HOLD" if r["severity"] == "HOLD" else "WARN"),
            )

    report = {
        "lint_version": rules.get("version", "1.0"),
        "result": result,
        "review_top5": top5(tb) if ("risk" in tb and "fhb_gate" in tb) else [],
        "errors": errors,
        "normalized": {
            "mode": tb.get("mode"),
            "state_target": tb.get("state_target"),
            "requires_human_approval": tb.get("hsp", {}).get("requires_human_approval", True),
            "approved_by_human": tb.get("hsp", {}).get("approved_by_human", False),
            "downgraded_claims": 0,
        },
    }
    return report


def main():
    if len(sys.argv) < 2:
        print("Usage: lint.py <tb_json_path>", file=sys.stderr)
        sys.exit(2)

    tb_path = Path(sys.argv[1])
    tb = json.loads(tb_path.read_text(encoding="utf-8"))
    rep = lint(tb)
    print(json.dumps(rep, ensure_ascii=False, indent=2))

    # exit code: PASS/WARN=0, HOLD=3, BLOCK=4
    if rep["result"] in ("PASS", "WARN"):
        sys.exit(0)
    elif rep["result"] == "HOLD":
        sys.exit(3)
    else:
        sys.exit(4)


if __name__ == "__main__":
    main()

