#!/usr/bin/env python3
"""ml/predict.py  --  score new incident narratives"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.artifacts import (  # noqa: E402
    ART,
    ModelUnavailable,
    load_tokenizer,
    read_run_meta,
    read_serving,
)
from ml.calibration import Calibrator  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

DEFAULT_THRESHOLD = 0.50
DEFAULT_MARGIN = 0.15

BANDS = ("HIGH", "ELEVATED", "BORDERLINE", "LOW")
GUIDANCE = {
    "HIGH": "Review first. Strong indicators of serious-injury potential.",
    "ELEVATED": "Flag for review.",
    "BORDERLINE": "Model is unsure - human judgement needed either way.",
    "LOW": "No action indicated by the model.",
}
LABELS = {
    "HIGH": "HIGH      -- review first",
    "ELEVATED": "ELEVATED  -- flag for review",
    "BORDERLINE": "BORDERLINE-- model is unsure",
    "LOW": "LOW       -- no action indicated",
}


def band(p: float, thr: float, margin: float = DEFAULT_MARGIN) -> str:
    """Four bands, not a yes/no."""
    if p >= thr + margin:
        return "HIGH"
    if p >= thr:
        return "ELEVATED"
    if p >= thr - margin:
        return "BORDERLINE"
    return "LOW"


def resolve_checkpoint(explicit: str | Path | None) -> tuple[Path, str]:
    """Return (checkpoint dir, how it was chosen)."""
    if explicit:
        p = Path(explicit)
        if not p.exists():
            raise ModelUnavailable(f"--model-dir {p} does not exist")
        return p, "given on the command line"

    served = read_serving()
    if served:
        return Path(served["checkpoint"]), "model_artifacts/SERVING.json"

    cands = sorted(ART.glob("**/run_meta.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if cands:
        return cands[0].parent, f"most recent run_meta.json ({cands[0].parent.name})"

    legacy = ART / "deberta_sif" / "seed0"
    if legacy.exists():
        return legacy, "legacy path, no run_meta.json -- VERIFY THIS"

    raise ModelUnavailable(
        "No model found. Fetch the trained one:\n"
        "  python -m ml.fetch_model\n"
        "or train one:\n"
        "  python -m ml.train_deberta --init-from model_artifacts/deberta_phmsa_stilt --seeds 3"
    )


class Scorer:
    """Loads a checkpoint with its calibration. ONNX if exported, else PyTorch."""

    def __init__(self, model_dir: str | Path | None = None, max_length: int = 256):
        self.ckpt, self.chosen_by = resolve_checkpoint(model_dir)
        self.max_length = max_length
        self.meta = read_run_meta(self.ckpt) or {}

        served = read_serving() or {}
        onnx_dir = Path(served["onnx_dir"]) if (
            served.get("onnx_dir") and not model_dir
            and Path(served["checkpoint"]) == self.ckpt
        ) else self.ckpt / "onnx"

        self.tok = load_tokenizer(self.ckpt, onnx_dir)

        cal_path = next((p for p in (self.ckpt / "calibration.json",
                                     onnx_dir / "calibration.json") if p.exists()), None)
        self.calibrator = Calibrator.load(cal_path) if cal_path else Calibrator.identity()
        self.calibrated = cal_path is not None

        onnx_path = next((p for p in (onnx_dir / "model.int8.onnx", onnx_dir / "model.onnx")
                          if p.exists()), None)
        if onnx_path is not None:
            import onnxruntime as ort

            self.sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
            self.names = {i.name for i in self.sess.get_inputs()}
            self.backend = (f"onnx ({onnx_path.name}, "
                            f"{onnx_path.stat().st_size/1e6:.0f} MB, CPU)")
            self.torch_model = None
        else:
            import torch
            from transformers import AutoModelForSequenceClassification

            self.torch = torch
            self.torch_model = (
                AutoModelForSequenceClassification.from_pretrained(self.ckpt).float().eval()
            )
            self.backend = f"pytorch ({self.ckpt.name})"

    def threshold(self, explicit: float | None = None) -> tuple[float, str]:
        if explicit is not None:
            return explicit, "given explicitly"
        if self.meta.get("threshold") is not None:
            return float(self.meta["threshold"]), (
                f"run_meta.json in {self.ckpt.name} "
                f"({self.meta.get('threshold_reason', 'validation-selected')})"
            )
        return DEFAULT_THRESHOLD, "built-in default -- no run_meta.json; VERIFY THIS"

    @property
    def band_margin(self) -> float:
        """A margin the loaded model can actually populate."""
        stored = self.meta.get("band_margin")
        if stored:
            return float(stored)
        if self.calibrated:
            return DEFAULT_MARGIN
        span = self.meta.get("raw_score_span")
        return max(0.01, min(DEFAULT_MARGIN, float(span) / 4)) if span else DEFAULT_MARGIN

    def raw(self, texts: list[str], batch_size: int = 16) -> np.ndarray:
        out = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            if self.torch_model is None:
                enc = self.tok(batch, truncation=True, max_length=self.max_length,
                               padding=True, return_tensors="np")
                feed = {k: v.astype(np.int64) for k, v in enc.items() if k in self.names}
                logits = self.sess.run(None, feed)[0]
                e = np.exp(logits - logits.max(axis=1, keepdims=True))
                out.append((e / e.sum(axis=1, keepdims=True))[:, 1])
            else:
                enc = self.tok(batch, truncation=True, max_length=self.max_length,
                               padding=True, return_tensors="pt")
                with self.torch.no_grad():
                    logits = self.torch_model(**enc).logits
                out.append(self.torch.softmax(logits, dim=-1)[:, 1].numpy())
        return np.concatenate(out)

    def __call__(self, texts: list[str], batch_size: int = 16) -> np.ndarray:
        """Calibrated probabilities. Monotonic in the raw score, so ranking is"""
        return self.calibrator(self.raw(texts, batch_size))

    def describe(self) -> str:
        lines = [f"[model]     {self.backend}",
                 f"[checkpoint] {self.ckpt}  ({self.chosen_by})"]
        if self.meta.get("source"):
            lines.append(f"[source]    {self.meta['source']}")
        lines.append(f"[calibration] {self.calibrator.method}"
                     + ("" if self.calibrated else "  -- NONE FOUND, probabilities are raw"))
        return "\n".join(lines)


def show(text: str, p: float, thr: float, margin: float) -> None:
    print(f"\n  {text[:110]}{'...' if len(text) > 110 else ''}")
    print(f"    SIF probability : {p:.3f}   (threshold {thr:.3f})")
    print(f"    {LABELS[band(p, thr, margin)]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", help="a single narrative")
    ap.add_argument("--file", help="text file, one narrative per line")
    ap.add_argument("--csv", help="CSV with a narrative_text column")
    ap.add_argument("--out", help="where to write the scored CSV")
    ap.add_argument("--model-dir", default=None,
                    help="checkpoint dir (default: SERVING.json, then newest run)")
    ap.add_argument("--threshold", type=float, default=None)
    ap.add_argument("--margin", type=float, default=None, help="band width around the threshold")
    ap.add_argument("--top", type=int, default=20, help="how many to show for batch input")
    ap.add_argument("--top-frac", type=float, default=None,
                    help="flag the top fraction of the batch by rank instead of by "
                         "absolute threshold (e.g. 0.15). Robust to domain shift.")
    args = ap.parse_args()

    try:
        scorer = Scorer(args.model_dir)
    except ModelUnavailable as exc:
        raise SystemExit(str(exc))
    thr, why = scorer.threshold(args.threshold)
    margin = args.margin if args.margin is not None else scorer.band_margin
    print(scorer.describe())
    print(f"[threshold] {thr:.3f}  ({why})")

    if args.csv:
        import pandas as pd

        df = pd.read_csv(args.csv)
        col = "narrative_text" if "narrative_text" in df.columns else df.columns[0]
        df["sif_probability"] = scorer(df[col].astype(str).tolist())
        df = df.sort_values("sif_probability", ascending=False).reset_index(drop=True)

        if args.top_frac:
            k = max(1, int(round(len(df) * args.top_frac)))
            df["sif_flag"] = np.where(np.arange(len(df)) < k, "REVIEW", "-")
            rule = f"top {args.top_frac:.0%} by rank ({k} of {len(df)})"
        else:
            df["sif_flag"] = np.where(df.sif_probability >= thr, "REVIEW", "-")
            rule = f"probability >= {thr:.3f}"
        df["sif_band"] = [band(p, thr, margin) for p in df.sif_probability]

        out = args.out or "scored.csv"
        df.to_csv(out, index=False)
        lo, hi = df.sif_probability.min(), df.sif_probability.max()
        print(f"\nscored {len(df)} reports -> {out}")
        print(f"score range {lo:.3f} - {hi:.3f} (spread {hi-lo:.3f})")
        if hi - lo < 0.05:
            print("  note: narrow spread. Ranking can still be good -- PR-AUC and ROC-AUC")
            print("  measure order, not absolute values -- but an absolute threshold is")
            print("  not trustworthy here. Prefer --top-frac.")
        print(f"flagged by {rule}: {(df.sif_flag == 'REVIEW').sum()} of {len(df)}")
        print("bands: " + ", ".join(f"{b}={int((df.sif_band == b).sum())}" for b in BANDS))
        print(f"\nTop {min(args.top, len(df))} by risk:")
        for _, r in df.head(args.top).iterrows():
            show(str(r[col]), r.sif_probability, thr, margin)
        return

    if args.file:
        texts = [l.strip() for l in
                 Path(args.file).read_text(encoding="utf-8").splitlines() if l.strip()]
    elif args.text:
        texts = [args.text]
    else:
        print("\nPaste a narrative and press Enter. Blank line or Ctrl+C to quit.")
        while True:
            try:
                line = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if not line:
                return
            show(line, float(scorer([line])[0]), thr, margin)

    scores = scorer(texts)
    for i in np.argsort(-scores)[: args.top]:
        show(texts[i], float(scores[i]), thr, margin)
    print(f"\n{int((scores >= thr).sum())} of {len(texts)} above threshold")


if __name__ == "__main__":
    main()
