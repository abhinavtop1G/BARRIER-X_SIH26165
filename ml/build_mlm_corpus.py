#!/usr/bin/env python3
"""ml/build_mlm_corpus.py"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "mlm_corpus.txt"
STATS = ROOT / "data" / "reports" / "mlm_corpus_stats.json"

NARRATIVE_COLUMNS = [
    "narrative_text",
    "Description Of Events",
    "Final Narrative",
    "Abstract Text",
    "text",
    "Description",
    "report_text", "summary", "narrative",
]

SEARCH_DIRS = [
    ROOT / "data" / "raw",
]

MIN_CHARS = 60
MAX_CHARS = 4000


def normalise(text: str) -> str:
    return " ".join(str(text).lower().split())


def sha(text: str) -> str:
    return hashlib.sha1(normalise(text).encode()).hexdigest()


def held_out_hashes() -> set[str]:
    """Frozen test + real validation narratives. Never enter the corpus."""
    out: set[str] = set()
    for path in (
        ROOT / "data" / "splits" / "test.csv",
        ROOT / "data" / "splits" / "validation.csv",
    ):
        if path.exists():
            for t in pd.read_csv(path)["narrative_text"].dropna().astype(str):
                out.add(sha(t))
    return out


def find_narrative_column(path: Path) -> str | None:
    try:
        head = pd.read_csv(path, nrows=5, low_memory=False, on_bad_lines="skip")
    except Exception:
        return None
    for col in NARRATIVE_COLUMNS:
        if col in head.columns:
            return col
    return None


def discover(extra: list[str]) -> list[tuple[Path, str]]:
    found: list[tuple[Path, str]] = []
    seen: set[Path] = set()
    candidates = [p for d in SEARCH_DIRS if d.exists() for p in d.rglob("*.csv")]
    candidates += [Path(p) for p in extra]
    for path in sorted(candidates):
        if path in seen or not path.exists():
            continue
        seen.add(path)
        if "splits" in path.parts or path.parent.name == "reports":
            continue
        col = find_narrative_column(path)
        if col:
            found.append((path, col))
    return found


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--extra", nargs="*", default=[], help="additional CSV paths")
    ap.add_argument("--min-chars", type=int, default=MIN_CHARS)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    blocked = held_out_hashes()
    print(f"[guard] {len(blocked)} held-out narratives excluded by hash\n")

    sources = discover(args.extra)
    if not sources:
        raise SystemExit(
            "No CSVs with a recognised narrative column found.\n"
            f"Searched: {[str(d) for d in SEARCH_DIRS]}\n"
            "Pass files explicitly with --extra, or add the column name to NARRATIVE_COLUMNS."
        )

    seen: set[str] = set()
    per_source: dict[str, int] = {}
    kept = skipped_dupe = skipped_short = skipped_heldout = 0

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8") as fh:
        for path, col in sources:
            n_here = 0
            try:
                reader = pd.read_csv(
                    path, usecols=[col], chunksize=100_000, low_memory=False, on_bad_lines="skip"
                )
            except Exception as exc:
                print(f"  [skip] {path.name}: {exc}")
                continue

            for chunk in reader:
                for raw in chunk[col].dropna().astype(str):
                    text = " ".join(raw.split())
                    if len(text) < args.min_chars:
                        skipped_short += 1
                        continue
                    if len(text) > MAX_CHARS:
                        text = text[:MAX_CHARS]
                    h = sha(text)
                    if h in blocked:
                        skipped_heldout += 1
                        continue
                    if h in seen:
                        skipped_dupe += 1
                        continue
                    seen.add(h)
                    fh.write(text + "\n")
                    kept += 1
                    n_here += 1

            per_source[str(path.relative_to(ROOT) if ROOT in path.parents else path)] = n_here
            print(f"  {n_here:>9,}  {path.name}  (column: {col})")

    stats = {
        "output": str(out_path),
        "rows_kept": kept,
        "skipped_duplicate": skipped_dupe,
        "skipped_too_short": skipped_short,
        "skipped_held_out": skipped_heldout,
        "per_source": per_source,
        "size_mb": round(out_path.stat().st_size / 1e6, 1),
    }
    STATS.parent.mkdir(parents=True, exist_ok=True)
    STATS.write_text(json.dumps(stats, indent=2))

    print(f"\n  kept          {kept:>10,}")
    print(f"  dropped dupe  {skipped_dupe:>10,}")
    print(f"  dropped short {skipped_short:>10,}")
    print(f"  dropped held-out {skipped_heldout:>7,}   (0 is normal: external sources\n                                    share no text with the seed set)")
    print(f"\nwrote -> {out_path}  ({stats['size_mb']} MB)")


if __name__ == "__main__":
    main()
