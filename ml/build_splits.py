#!/usr/bin/env python3
"""ml/build_splits.py  --  train / validation / test from our own seed set"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SEED_FILE = ROOT / "data" / "seed" / "seed_labeled.csv"
OUT = ROOT / "data" / "splits"

TEST_FRAC = 0.30
VAL_FRAC = 0.20
SEED = 42


def normalise(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().str.replace(r"\s+", " ", regex=True).str.strip()


def take_groups(df: pd.DataFrame, frac: float, seed: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split off `frac` of rows, stratified on label, moving whole"""
    df = df.assign(_grp=normalise(df["narrative_text"]))
    groups = (
        df.groupby("_grp")
        .agg(n=("record_id", "size"), label=("sif_potential", "first"))
        .reset_index()
    )
    picked: list[str] = []
    for _, block in groups.groupby("label"):
        block = block.sample(frac=1.0, random_state=seed)
        budget, taken = round(block["n"].sum() * frac), 0
        for _, row in block.iterrows():
            if taken >= budget:
                break
            picked.append(row["_grp"])
            taken += row["n"]
    held = df[df["_grp"].isin(picked)].drop(columns="_grp").reset_index(drop=True)
    rest = df[~df["_grp"].isin(picked)].drop(columns="_grp").reset_index(drop=True)
    return held, rest


def audit(splits: dict[str, pd.DataFrame]) -> dict:
    print(f"{'split':<12}{'rows':>7}{'Yes':>6}{'No':>6}{'base rate':>12}{'mean chars':>12}")
    stats = {}
    for name, d in splits.items():
        vc = d["sif_potential"].value_counts()
        rate = (d["sif_potential"] == "Yes").mean()
        chars = d["narrative_text"].astype(str).str.len().mean()
        print(f"{name:<12}{len(d):>7}{vc.get('Yes', 0):>6}{vc.get('No', 0):>6}"
              f"{rate:>12.3f}{chars:>12.0f}")
        stats[name] = {"rows": len(d), "yes": int(vc.get("Yes", 0)),
                       "no": int(vc.get("No", 0)), "base_rate": round(float(rate), 4)}

    print("\nleakage check (normalised narrative overlap):")
    keys = list(splits)
    clean = True
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = keys[i], keys[j]
            overlap = set(normalise(splits[a]["narrative_text"])) & set(
                normalise(splits[b]["narrative_text"]))
            clean &= not overlap
            print(f"  {a:<11} vs {b:<11} {len(overlap):>4}  "
                  f"{'OK' if not overlap else '*** LEAK ***'}")
    stats["leakage_free"] = clean
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-frac", type=float, default=TEST_FRAC)
    ap.add_argument("--val-frac", type=float, default=VAL_FRAC)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    if not SEED_FILE.exists():
        raise SystemExit(f"{SEED_FILE} not found. Run: python data/build_seed.py")

    df = pd.read_csv(SEED_FILE)
    print(f"[seed] {len(df)} labelled rows\n")

    test, rest = take_groups(df, args.test_frac, args.seed)
    val, train = take_groups(rest, args.val_frac, args.seed + 1)
    splits = {"train": train, "validation": val, "test": test}

    stats = audit(splits)

    if args.write:
        if (OUT / "test.csv").exists():
            print(f"\n[!] {OUT/'test.csv'} already exists.")
            print("    The test set is meant to be frozen once you start reporting numbers.")
            print("    Delete it deliberately if you really mean to regenerate.")
            return
        OUT.mkdir(parents=True, exist_ok=True)
        for name, d in splits.items():
            d.to_csv(OUT / f"{name}.csv", index=False)
        (ROOT / "data" / "reports").mkdir(parents=True, exist_ok=True)
        (ROOT / "data" / "reports" / "split_stats.json").write_text(json.dumps(stats, indent=2))
        print(f"\nwrote -> {OUT}")
        print("Next: python ml/train_deberta.py --seeds 3")


if __name__ == "__main__":
    main()
