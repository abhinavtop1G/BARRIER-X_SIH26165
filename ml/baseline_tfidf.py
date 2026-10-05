#!/usr/bin/env python3
"""ml/baseline_tfidf.py  --  the control every transformer result needs"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml.evaluation import evaluate, select_threshold  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "data" / "reports"
PHMSA = ROOT / "data" / "seed" / "phmsa_serious.csv"

TEXT = "narrative_text"
LABEL = "sif_potential"


def fit_score(train_text, train_y, frames, ngram, max_features):
    vec = TfidfVectorizer(ngram_range=ngram, max_features=max_features,
                          sublinear_tf=True, min_df=2, stop_words="english")
    X = vec.fit_transform(train_text)
    clf = LogisticRegression(class_weight="balanced", max_iter=2000, C=1.0,
                             random_state=42).fit(X, train_y)
    return {k: clf.predict_proba(vec.transform(v[TEXT].astype(str)))[:, 1]
            for k, v in frames.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--precision-floor", type=float, default=0.50)
    ap.add_argument("--max-features", type=int, default=20000)
    ap.add_argument("--skip-phmsa", action="store_true")
    args = ap.parse_args()

    frames = {name: pd.read_csv(ROOT / "data" / "splits" / f"{name}.csv")
              for name in ("train", "validation", "test")}
    y = {k: (v[LABEL] == "Yes").astype(int).to_numpy() for k, v in frames.items()}

    conditions = [("IHM only", frames["train"][TEXT].astype(str), y["train"])]

    if PHMSA.exists() and not args.skip_phmsa:
        ph = pd.read_csv(PHMSA)
        ph = ph[ph.split == "train"]
        ph_text, ph_y = ph[TEXT].astype(str), (ph[LABEL] == "Yes").astype(int).to_numpy()
        conditions += [
            ("PHMSA only", ph_text, ph_y),
            ("PHMSA + IHM",
             pd.concat([ph_text, frames["train"][TEXT].astype(str)], ignore_index=True),
             pd.concat([pd.Series(ph_y), pd.Series(y["train"])], ignore_index=True).to_numpy()),
        ]
    elif not args.skip_phmsa:
        print(f"[note] {PHMSA} absent -- run data/build_phmsa.py for the PHMSA controls\n")

    rows = []
    for cond, tr_text, tr_y in conditions:
        for ngram, tag in (((1, 1), "unigram"), ((1, 2), "uni+bigram")):
            s = fit_score(tr_text, tr_y, frames, ngram, args.max_features)
            thr, reason = select_threshold(y["validation"], s["validation"], args.precision_floor)
            rep = evaluate(f"TF-IDF+LR [{cond}] ({tag})", y["test"], s["test"], thr, reason)
            print(rep.pretty() + "\n")
            rows.append(rep.to_row())

    REPORTS.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(REPORTS / "baseline_tfidf.csv", index=False)
    (REPORTS / "baseline_tfidf.json").write_text(json.dumps(rows, indent=2))

    print("-" * 68)
    for cond, _, _ in conditions:
        best = max((r["pr_auc"] for r in rows if f"[{cond}]" in r["model"]), default=float("nan"))
        print(f"  best PR-AUC, {cond:<12} = {best:.4f}")
    print("\nCompare against the DeBERTa per-seed mean. If the gap is smaller than the")
    print("DeBERTa seed std, the transformer is not yet distinguishable from word counts.")
    print("If PHMSA helps TF-IDF as much as it helps the transformer, the STILT gain was")
    print("about data volume, not representation -- say so.")


if __name__ == "__main__":
    main()
