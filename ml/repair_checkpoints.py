#!/usr/bin/env python3
"""ml/repair_checkpoints.py  --  make checkpoints loadable across transformers versions"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "model_artifacts"


def repair(path: Path, check: bool) -> str:
    """Return one of: 'ok', 'repaired', 'would-repair', 'unreadable'."""
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return "unreadable"
    est = cfg.get("extra_special_tokens")
    if not isinstance(est, list):
        return "ok"
    if check:
        return "would-repair"
    cfg.pop("extra_special_tokens")
    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    return "repaired"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ART))
    ap.add_argument("--check", action="store_true", help="report only, change nothing")
    args = ap.parse_args()

    root = Path(args.root)
    files = sorted(root.rglob("tokenizer_config.json"))
    if not files:
        raise SystemExit(f"No tokenizer_config.json found under {root}")

    counts: dict[str, int] = {}
    for f in files:
        status = repair(f, args.check)
        counts[status] = counts.get(status, 0) + 1
        if status != "ok":
            print(f"  [{status:<13}] {f.relative_to(root)}")

    print(f"\n  {len(files)} tokenizer_config.json scanned")
    for k, v in sorted(counts.items()):
        print(f"    {k:<13} {v}")
    if args.check and counts.get("would-repair"):
        print("\n  Run without --check to apply.")


if __name__ == "__main__":
    main()
