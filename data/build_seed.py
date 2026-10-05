#!/usr/bin/env python3
"""data/build_seed.py  --  build the labelled seed set from the public source"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "seed" / "seed_labeled.csv"

SIF_YES = {"IV", "V", "VI"}

CANDIDATE_NAMES = [
    "IHMStefanini_industrial_safety_and_health_database_with_accidents_description.csv",
    "IHMStefanini_industrial_safety_and_health_database.csv",
    "industrial_safety_and_health_database_with_accidents_description.csv",
    "IHM.csv",
]

NARRATIVE_CANDIDATES = ["Description", "description", "Accident Description"]
LEVEL_CANDIDATES = ["Potential Accident Level", "Potential_Accident_Level", "Potential Accident level"]
RISK_CANDIDATES = ["Critical Risk", "Critical_Risk", "Risk"]


def find_source() -> Path:
    for name in CANDIDATE_NAMES:
        for hit in RAW.rglob(name):
            return hit
    for path in RAW.rglob("*.csv"):
        try:
            head = pd.read_csv(path, nrows=3, low_memory=False, on_bad_lines="skip")
        except Exception:
            continue
        if any(c in head.columns for c in LEVEL_CANDIDATES):
            return path
    raise SystemExit(
        "IHM Stefanini CSV not found under data/raw/.\n"
        "Download it first:\n"
        "  kaggle datasets download -d ihmstefanini/"
        "industrial-safety-and-health-analytics-database\n"
        "  unzip -o industrial-safety-and-health-analytics-database.zip -d data/raw/"
    )


def pick(df: pd.DataFrame, candidates: list[str], what: str) -> str:
    for c in candidates:
        if c in df.columns:
            return c
    raise SystemExit(f"No {what} column found. Columns present: {list(df.columns)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-chars", type=int, default=40)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()

    src = find_source()
    print(f"[source] {src}")
    raw = pd.read_csv(src, low_memory=False)
    print(f"[source] {len(raw)} rows, {len(raw.columns)} columns")

    text_col = pick(raw, NARRATIVE_CANDIDATES, "narrative")
    level_col = pick(raw, LEVEL_CANDIDATES, "potential accident level")

    df = pd.DataFrame({
        "narrative_text": raw[text_col].astype(str).str.replace(r"\s+", " ", regex=True).str.strip(),
        "potential_accident_level": raw[level_col].astype(str).str.strip().str.upper(),
    })
    for col, cands in (("critical_risk", RISK_CANDIDATES),
                       ("industry_sector", ["Industry Sector", "Industry_Sector"]),
                       ("country", ["Countries", "Country"])):
        for c in cands:
            if c in raw.columns:
                df[col] = raw[c].astype(str).str.strip()
                break

    before = len(df)
    df = df[df.narrative_text.str.len() >= args.min_chars]
    df = df.loc[~df.narrative_text.str.lower().duplicated()].reset_index(drop=True)
    print(f"[clean] {before} -> {len(df)} after dropping short and duplicate narratives")

    df["sif_potential"] = df.potential_accident_level.map(
        lambda lv: "Yes" if lv in SIF_YES else "No"
    )
    df["source_dataset"] = "ihm_stefanini_kaggle_cc0"
    df["label_source"] = "derived: Potential Accident Level >= IV"
    df["record_id"] = [f"ihm_{i:05d}" for i in range(len(df))]

    print("\n[levels]")
    print(df.potential_accident_level.value_counts().sort_index().to_string())
    print("\n[labels]", df.sif_potential.value_counts().to_dict())
    print(f"[labels] base rate = {(df.sif_potential == 'Yes').mean():.3f}")
    print(f"[text]   mean length = {int(df.narrative_text.str.len().mean())} chars")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    print(f"\nwrote -> {out}  ({len(df)} rows)")
    print("Next: python ml/build_splits.py --write")


if __name__ == "__main__":
    main()
