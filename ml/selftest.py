#!/usr/bin/env python3
"""ml/selftest.py  --  does the deployed system actually work?"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.evaluation import evaluate  # noqa: E402
from ml.predict import BANDS, Scorer, band  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TEST = ROOT / "data" / "splits" / "test.csv"

HIGH_POTENTIAL = [
    "A crane load was swung over an occupied walkway during a lift. No one was struck "
    "and work continued.",
    "Gas detector alarmed at 15% LEL beside an open drain during hot work preparation. "
    "Work was stopped before an ignition source was introduced.",
    "A scaffold plank slipped as the worker stepped onto it at 8 metres. He regained "
    "his balance and was not injured.",
    "A reversing vehicle came within one metre of a banksman who had not heard it. "
    "There was no contact.",
    "Pressure was found still trapped in a line that had been signed off as isolated, "
    "discovered before the flange was broken.",
    "H2S alarm sounded at the wellhead; two technicians were working without breathing "
    "apparatus and one collapsed before rescue.",
    "Uncontrolled release of high pressure gas from a flange ignited, engulfing the "
    "platform in flame.",
    "During a workover at Duliajan the travelling block came down onto the rig floor "
    "while two crew were positioned beneath it.",
    "A worker entered a confined space vessel without a permit or gas test and lost "
    "consciousness.",
]
LOW_POTENTIAL = [
    "A worker cut his finger on a sheet metal edge and required a plaster from the "
    "first aid box.",
    "An employee strained his back lifting a 15 kg box of records and was sent home "
    "for the remainder of the shift.",
    "A technician twisted his ankle stepping off a kerb in the car park and was given "
    "an ice pack.",
    "An employee spilled coffee in the site office kitchen and wiped it up.",
    "The printer in the HSE office ran out of toner during the morning shift.",
    "A worker reported that the canteen microwave was dirty and requested cleaning.",
]
CONTROL = "aaaaaaaa bbbbbbbb cccccccc dddddddd eeeeeeee ffffffff gggggggg hhhhhhhh"

SEVERE, TRIVIAL = HIGH_POTENTIAL, LOW_POTENTIAL

results: list[tuple[bool, str, str]] = []


def check(ok: bool, label: str, detail: str = "") -> bool:
    results.append((ok, label, detail))
    print(f"{'[ OK ]' if ok else '[FAIL]'} {label}" + (f" -- {detail}" if detail else ""))
    return ok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", default=None)
    ap.add_argument("--strict-ood", action="store_true",
                    help="also require every severe probe to clear the threshold")
    args = ap.parse_args()

    print("=" * 72)
    print("BARRIER X selftest")
    print("=" * 72)

    print("\nCheckpoints")
    from ml.artifacts import ART, ModelUnavailable, load_tokenizer

    ckpts = sorted({p.parent for p in ART.rglob("tokenizer_config.json")})
    bad = []
    for c in ckpts:
        try:
            load_tokenizer(c)
        except (ModelUnavailable, SystemExit):
            bad.append(c.relative_to(ART))
    check(not bad, f"all {len(ckpts)} checkpoints load",
          "" if not bad else f"unloadable: {bad}. Run: python -m ml.repair_checkpoints")

    print("\nServed model")
    scorer = Scorer(args.model_dir)
    print(scorer.describe())
    thr, why = scorer.threshold()
    margin = scorer.band_margin
    print(f"[threshold] {thr:.4f}  ({why})")
    check(scorer.calibrated, "calibration present",
          "" if scorer.calibrated else "no calibration.json -- probabilities are raw")

    df = pd.read_csv(TEST)
    texts = df["narrative_text"].astype(str).tolist()
    y = (df["sif_potential"] == "Yes").astype(int).to_numpy()
    p = scorer(texts)
    raw = scorer.raw(texts)

    print("\nScore distribution")
    span_raw, span = float(raw.max() - raw.min()), float(p.max() - p.min())
    check(span_raw > 0.01, "model output is not a constant",
          f"raw span {span_raw:.4f} across {len(texts)} narratives")
    check(span > 0.20, "calibrated scores are usefully spread",
          f"span {span:.3f}  range [{p.min():.3f}, {p.max():.3f}]  (raw span {span_raw:.3f})")

    print("\nBands")
    counts = {b: int(sum(band(x, thr, margin) == b for x in p)) for b in BANDS}
    print(f"       margin {margin:.3f}  ->  " + ", ".join(f"{b}={counts[b]}" for b in BANDS))
    unreachable = [b for b in ("HIGH", "LOW") if thr + margin > 1.0 or thr - margin < 0.0] or [
        b for b in BANDS if counts[b] == 0
    ]
    check(all(counts[b] > 0 for b in BANDS), "all four bands populated on the test set",
          "" if all(counts[b] > 0 for b in BANDS) else f"empty: {unreachable}")

    flagged = int((p >= thr).sum())
    check(0 < flagged < len(p), "threshold splits the test set",
          f"{flagged} of {len(p)} flagged")

    print("\nRanking on the frozen test set")
    rep = evaluate("selftest", y, p, thr, why)
    print("  " + rep.pretty().replace("\n", "\n  "))
    check(rep.roc_auc > 0.60, "ROC-AUC beats chance", f"{rep.roc_auc:.4f}")
    check(rep.pr_auc > rep.base_rate + 0.10, "PR-AUC beats base rate by >0.10",
          f"{rep.pr_auc:.4f} vs base {rep.base_rate:.3f}")
    check(rep.triage["P@10"] >= 0.60, "precision@10 is useful for triage",
          f"P@10={rep.triage['P@10']:.3f}, lift={rep.triage['lift@10']:.2f}x")

    print("\nOut-of-domain probes (oil and gas, not the training distribution)")
    s_hi, s_lo = scorer(HIGH_POTENTIAL), scorer(LOW_POTENTIAL)
    s_ctl = float(scorer([CONTROL])[0])
    from sklearn.metrics import roc_auc_score

    yy = np.r_[np.ones(len(s_hi)), np.zeros(len(s_lo))]
    ss = np.r_[s_hi, s_lo]
    auc = roc_auc_score(yy, ss)
    k = 5
    top_k = np.argsort(-ss)[:k]
    p_at_k = float(yy[top_k].mean())

    print(f"       high potential  mean {s_hi.mean():.3f}  [{s_hi.min():.3f}, {s_hi.max():.3f}]  n={len(s_hi)}")
    print(f"       low potential   mean {s_lo.mean():.3f}  [{s_lo.min():.3f}, {s_lo.max():.3f}]  n={len(s_lo)}")
    print(f"       control (repeated letters) {s_ctl:.3f}")
    print(f"       flagged at the threshold: {int((s_hi >= thr).sum())}/{len(s_hi)} high, "
          f"{int((s_lo >= thr).sum())}/{len(s_lo)} low   <- why this is not asserted")

    check(auc >= 0.85, "high-potential narratives outrank low-potential ones",
          f"ROC-AUC {auc:.3f} over {len(yy)} probes")
    check(p_at_k >= 0.80, f"the top {k} of the queue are high-potential",
          f"precision@{k}={p_at_k:.2f}")
    check(s_hi.mean() - s_lo.mean() > 0.05, "the two classes are separated",
          f"gap {s_hi.mean() - s_lo.mean():.3f}")
    check(s_ctl < s_hi.mean(), "nonsense control scores below the high-potential mean",
          f"control {s_ctl:.3f} vs {s_hi.mean():.3f}")
    if args.strict_ood:
        n_flagged = int((s_hi >= thr).sum())
        check(n_flagged == len(s_hi),
              "every high-potential narrative clears the threshold (strict)",
              f"{n_flagged} of {len(s_hi)} -- expected to fail out of domain; "
              f"use top_frac instead")

    print("\nAPI")
    try:
        from api.main import GUIDANCE as API_GUIDANCE
        from api.main import band as api_band
        from ml.predict import GUIDANCE as ML_GUIDANCE
        from ml.predict import band as ml_band

        check(api_band is ml_band, "API and predict.py share one band definition",
              "" if api_band is ml_band else "they have drifted apart again")
        check(API_GUIDANCE is ML_GUIDANCE, "API and predict.py share one guidance table")
        from api.schemas import ScoreResponse

        fields = set(ScoreResponse.model_fields)
        check({"model", "calibration"} <= fields,
              "score responses are traceable to a checkpoint",
              f"fields: {sorted(fields)}")
    except Exception as exc:
        check(False, "API imports", f"{type(exc).__name__}: {exc}")

    failed = [r for r in results if not r[0]]
    print("\n" + "=" * 72)
    if failed:
        print(f"FAILED {len(failed)} of {len(results)} checks:")
        for _, label, detail in failed:
            print(f"  - {label}" + (f": {detail}" if detail else ""))
        print("=" * 72)
        return 1
    print(f"ALL {len(results)} CHECKS PASSED")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
