#!/usr/bin/env python3
"""data/build_phmsa.py  --  the intermediate supervised task"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "seed" / "phmsa_serious.csv"
STATS = ROOT / "data" / "reports" / "phmsa_stats.json"

TEXT_COL = "Description Of Events"
LABEL_COL = "Serious Incident Ind"
COMPONENTS = [
    "Hmis Serious Fatality", "Hmis Serious Injury", "Hmis Serious Evacuations",
    "Hmis Serious Major Artery", "Hmis Serious Bulk Release",
    "Hmis Serious Radioactive", "Hmis Serious Marine Pollutant",
]


def normalise(text: str) -> str:
    return " ".join(str(text).lower().split())


def sha(text: str) -> str:
    return hashlib.sha1(normalise(text).encode()).hexdigest()


def held_out_hashes() -> set[str]:
    out: set[str] = set()
    for name in ("test", "validation"):
        p = ROOT / "data" / "splits" / f"{name}.csv"
        if p.exists():
            for t in pd.read_csv(p)["narrative_text"].dropna().astype(str):
                out.add(sha(t))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-chars", type=int, default=60)
    ap.add_argument("--neg-ratio", type=float, default=4.0,
                    help="negatives kept per positive; 0 keeps all")
    ap.add_argument("--val-frac", type=float, default=0.05,
                    help="PHMSA-internal validation slice, to watch the intermediate task")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    files = sorted(glob.glob(str(RAW / "[12][09][0-9][0-9]-[01][0-9].csv")))
    if not files:
        raise SystemExit(f"No PHMSA monthly CSVs under {RAW}.")
    print(f"[source] {len(files)} PHMSA monthly files, "
          f"{Path(files[0]).stem} .. {Path(files[-1]).stem}")

    blocked = held_out_hashes()
    print(f"[guard]  {len(blocked)} held-out IHM narratives excluded by SHA-1")

    frames, skipped = [], 0
    for f in files:
        try:
            head = pd.read_csv(f, nrows=0, low_memory=False)
            cols = [c for c in [TEXT_COL, LABEL_COL] + COMPONENTS if c in head.columns]
            if TEXT_COL not in cols or LABEL_COL not in cols:
                skipped += 1
                continue
            frames.append(pd.read_csv(f, usecols=cols, low_memory=False, on_bad_lines="skip"))
        except Exception:
            skipped += 1
    print(f"[read]   {len(frames)} files usable, {skipped} skipped")

    df = pd.concat(frames, ignore_index=True)
    n_raw = len(df)

    df["narrative_text"] = (
        df[TEXT_COL].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    )
    df = df[df["narrative_text"].str.len() >= args.min_chars]
    n_long = len(df)
    df = df[df[LABEL_COL].isin(["Yes", "No"])]
    n_lab = len(df)
    df = df.drop_duplicates(subset="narrative_text")
    n_dedup = len(df)

    held = df["narrative_text"].map(sha).isin(blocked)
    n_held = int(held.sum())
    df = df[~held]

    df["sif_potential"] = np.where(df[LABEL_COL] == "Yes", "Yes", "No")
    present = [c for c in COMPONENTS if c in df.columns]
    if present:
        flags = df[present].eq("Yes")
        df["criteria"] = flags.apply(
            lambda r: "|".join(c.replace("Hmis Serious ", "") for c in present if r[c]), axis=1
        )
    else:
        df["criteria"] = ""

    pos = df[df.sif_potential == "Yes"]
    neg = df[df.sif_potential == "No"]
    print(f"\n[clean]  {n_raw:,} raw -> {n_long:,} long enough -> {n_lab:,} labelled "
          f"-> {n_dedup:,} deduplicated -> {len(df):,} after held-out guard ({n_held} removed)")
    print(f"[labels] {len(pos):,} serious / {len(neg):,} not  "
          f"(base rate {len(pos)/max(len(df),1):.2%})")

    rng = np.random.default_rng(args.seed)
    if args.neg_ratio and len(neg) > args.neg_ratio * len(pos):
        keep = rng.choice(len(neg), size=int(args.neg_ratio * len(pos)), replace=False)
        neg = neg.iloc[np.sort(keep)]
        print(f"[sample] negatives downsampled to {args.neg_ratio:g}:1 -> {len(neg):,}")

    out = pd.concat([pos, neg], ignore_index=True)
    out = out.iloc[rng.permutation(len(out))].reset_index(drop=True)

    n_val = int(len(out) * args.val_frac)
    out["split"] = "train"
    out.loc[: n_val - 1, "split"] = "validation"

    out["source_dataset"] = "phmsa_5800.1_usdot_public_domain"
    out["label_source"] = "Serious Incident Ind (49 CFR 171.16 serious-incident criteria)"
    out["record_id"] = [f"phmsa_{i:07d}" for i in range(len(out))]
    keep_cols = ["record_id", "narrative_text", "sif_potential", "criteria", "split",
                 "source_dataset", "label_source"]
    out = out[[c for c in keep_cols if c in out.columns]]

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.out, index=False)

    stats = {
        "files": len(files), "rows_raw": n_raw, "rows_long_enough": n_long,
        "rows_labelled": n_lab, "rows_deduplicated": n_dedup,
        "rows_held_out_removed": n_held, "rows_written": len(out),
        "positives_written": int((out.sif_potential == "Yes").sum()),
        "base_rate_written": round(float((out.sif_potential == "Yes").mean()), 4),
        "base_rate_full": round(len(pos) / max(n_dedup, 1), 4),
        "neg_ratio": args.neg_ratio,
        "mean_chars": int(out.narrative_text.str.len().mean()),
        "validation_rows": int((out.split == "validation").sum()),
    }
    STATS.parent.mkdir(parents=True, exist_ok=True)
    STATS.write_text(json.dumps(stats, indent=2))

    print(f"\n[write]  {len(out):,} rows -> {args.out}")
    print(f"         {stats['positives_written']:,} serious "
          f"({stats['base_rate_written']:.1%}), mean {stats['mean_chars']} chars, "
          f"{stats['validation_rows']:,} held for PHMSA-internal validation")
    print(f"[write]  stats -> {STATS}")
    if n_held:
        print(f"\n  NOTE: {n_held} held-out IHM narratives were found in PHMSA and removed.")
    print("\nNext: python -m ml.train_stilt")


if __name__ == "__main__":
    main()
