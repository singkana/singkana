#!/usr/bin/env python3
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "state" / "registry.json"


def canonical_json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def chain_hash(prev_hash: str, entry_without_hash: dict) -> str:
    h = hashlib.sha256()
    h.update(prev_hash.encode("utf-8"))
    h.update(b"\n")
    h.update(canonical_json(entry_without_hash).encode("utf-8"))
    return "sha256:" + h.hexdigest()


def verify_list(entries: list[dict], *, list_name: str) -> list[str]:
    errors: list[str] = []
    prev = "LEGACY"
    for i, e in enumerate(entries):
        if e.get("legacy") is True and "entry_hash" not in e:
            # legacyは鎖の外（境界明示）
            continue

        entry_hash = e.get("entry_hash")
        prev_hash = e.get("prev_hash")
        if not isinstance(entry_hash, str) or not entry_hash.startswith("sha256:"):
            errors.append(f"{list_name}[{i}]: missing/invalid entry_hash")
            continue
        if not isinstance(prev_hash, str):
            errors.append(f"{list_name}[{i}]: missing prev_hash")
            continue

        # prevの期待値：最初の鎖エントリは LEGACY、それ以降は前のentry_hash
        if prev_hash != prev:
            errors.append(f"{list_name}[{i}]: prev_hash mismatch (got {prev_hash}, expected {prev})")

        # hash再計算
        tmp = dict(e)
        tmp.pop("entry_hash", None)
        computed = chain_hash(prev_hash, tmp)
        if computed != entry_hash:
            errors.append(f"{list_name}[{i}]: entry_hash mismatch")

        prev = entry_hash
    return errors


def main():
    reg = json.loads(REGISTRY.read_text(encoding="utf-8"))
    ad = reg.get("adoptions") or []
    rj = reg.get("rejections") or []

    errors = []
    errors += verify_list(ad, list_name="adoptions")
    errors += verify_list(rj, list_name="rejections")

    out = {"ok": len(errors) == 0, "errors": errors}
    print(json.dumps(out, ensure_ascii=False, indent=2))
    sys.exit(0 if out["ok"] else 4)


if __name__ == "__main__":
    main()

