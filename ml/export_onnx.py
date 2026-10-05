#!/usr/bin/env python3
"""ml/export_onnx.py  --  make a fine-tuned checkpoint deployable, and prove it still works"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import average_precision_score, roc_auc_score
from transformers import AutoModelForSequenceClassification

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.artifacts import load_tokenizer, promote as promote_checkpoint, read_run_meta  # noqa: E402
from ml.calibration import Calibrator  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
TEST = ROOT / "data" / "splits" / "test.csv"

FP32_MAX_DELTA = 1e-3
INT8_MAX_PR_AUC_DROP = 0.02
INT8_MIN_SPEARMAN = 0.95
MIN_SCORE_SPAN = 0.01


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    from scipy.stats import spearmanr

    r = spearmanr(a, b).statistic
    return float(r) if np.isfinite(r) else 0.0


def torch_scores(ckpt: Path, texts: list[str], max_length: int) -> np.ndarray:
    tok = load_tokenizer(ckpt)
    model = AutoModelForSequenceClassification.from_pretrained(ckpt).float().eval()
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), 32):
            enc = tok(texts[i : i + 32], truncation=True, max_length=max_length,
                      padding=True, return_tensors="pt")
            out.append(torch.softmax(model(**enc).logits, dim=-1)[:, 1].numpy())
    return np.concatenate(out)


def onnx_scores(onnx_path: Path, tok_dir: Path, texts: list[str],
                max_length: int) -> tuple[np.ndarray, float]:
    import onnxruntime as ort

    tok = load_tokenizer(tok_dir)
    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    names = {i.name for i in sess.get_inputs()}
    out, t0 = [], time.perf_counter()
    for i in range(0, len(texts), 32):
        enc = tok(texts[i : i + 32], truncation=True, max_length=max_length,
                  padding=True, return_tensors="np")
        feed = {k: v.astype(np.int64) for k, v in enc.items() if k in names}
        logits = sess.run(None, feed)[0]
        e = np.exp(logits - logits.max(axis=1, keepdims=True))
        out.append((e / e.sum(axis=1, keepdims=True))[:, 1])
    return np.concatenate(out), (time.perf_counter() - t0) * 1000 / len(texts)


def export_fp32(ckpt: Path, out_dir: Path) -> Path:
    """Export via optimum. Never torch.onnx.export -- see the module docstring."""
    from optimum.onnxruntime import ORTModelForSequenceClassification

    print("[export] optimum -> ONNX fp32")
    model = ORTModelForSequenceClassification.from_pretrained(ckpt, export=True)
    model.save_pretrained(out_dir)
    produced = sorted(out_dir.glob("*.onnx"))
    if not produced:
        raise SystemExit(f"optimum produced no .onnx under {out_dir}")
    fp32 = out_dir / "model.onnx"
    if not fp32.exists():
        shutil.move(str(produced[0]), str(fp32))
    return fp32


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--out-dir", default=None, help="default: <checkpoint>/onnx")
    ap.add_argument("--max-length", type=int, default=256)
    ap.add_argument("--promote", action="store_true",
                    help="on success, mark this checkpoint for serving in SERVING.json")
    args = ap.parse_args()

    ckpt = Path(args.checkpoint)
    if not ckpt.exists():
        raise SystemExit(f"{ckpt} does not exist")
    out_dir = Path(args.out_dir) if args.out_dir else ckpt / "onnx"
    out_dir.mkdir(parents=True, exist_ok=True)

    tok = load_tokenizer(ckpt)
    tok.save_pretrained(out_dir)

    fp32 = export_fp32(ckpt, out_dir)
    print(f"[fp32] {fp32}  {fp32.stat().st_size/1e6:.1f} MB")

    from onnxruntime.quantization import QuantType, quantize_dynamic

    int8 = out_dir / "model.int8.onnx"
    quantize_dynamic(str(fp32), str(int8), weight_type=QuantType.QInt8)
    print(f"[int8] {int8}  {int8.stat().st_size/1e6:.1f} MB")

    df = pd.read_csv(TEST)
    texts = df["narrative_text"].astype(str).tolist()
    y = (df["sif_potential"] == "Yes").astype(int).to_numpy()

    s_t = torch_scores(ckpt, texts, args.max_length)
    s_f, lat_f = onnx_scores(fp32, out_dir, texts, args.max_length)
    s_i, lat_i = onnx_scores(int8, out_dir, texts, args.max_length)
    ref = average_precision_score(y, s_t)

    rows = [("pytorch fp32", s_t, float("nan")), ("onnx fp32", s_f, lat_f),
            ("onnx int8", s_i, lat_i)]
    print(f"\nfidelity on the frozen test set ({len(texts)} rows):")
    for tag, s, lat in rows:
        print(f"  {tag:<14} PR-AUC={average_precision_score(y, s):.4f}  "
              f"ROC-AUC={roc_auc_score(y, s):.4f}  span={s.max()-s.min():.4f}  "
              f"max|delta|={np.abs(s - s_t).max():.6f}  "
              f"spearman={spearman(s, s_t):.4f}  latency={lat:.1f} ms/doc")

    fatal: list[str] = []
    int8_bad: list[str] = []

    def deadness(tag: str, s: np.ndarray) -> list[str]:
        out = []
        span = float(s.max() - s.min())
        if span < MIN_SCORE_SPAN:
            out.append(f"score span {span:.5f} across {len(texts)} different narratives -- "
                       f"this export emits a constant; it is dead, not lossy")
        if roc_auc_score(y, s) < 0.55:
            out.append(f"ROC-AUC {roc_auc_score(y, s):.4f} is at or near chance")
        return out

    fatal += [f"onnx fp32: {m}" for m in deadness("onnx fp32", s_f)]
    delta_fp32 = float(np.abs(s_f - s_t).max())
    if delta_fp32 > FP32_MAX_DELTA:
        fatal.append(
            f"onnx fp32: max|delta| {delta_fp32:.6f} exceeds {FP32_MAX_DELTA}. A correct "
            f"fp32 conversion is numerically identical to PyTorch, so this means the "
            f"conversion is wrong, not that precision was lost."
        )

    int8_bad += deadness("onnx int8", s_i)
    drop_int8 = ref - average_precision_score(y, s_i)
    rho_int8 = spearman(s_i, s_t)
    if drop_int8 > INT8_MAX_PR_AUC_DROP:
        int8_bad.append(f"PR-AUC {drop_int8:.4f} below PyTorch (limit {INT8_MAX_PR_AUC_DROP})")
    if rho_int8 < INT8_MIN_SPEARMAN:
        int8_bad.append(
            f"rank correlation with fp32 is only {rho_int8:.4f} (need {INT8_MIN_SPEARMAN}). "
            f"The queue order is the product, and quantisation reshuffled it. Aggregate "
            f"metrics can look fine -- even better -- while the ranking has changed."
        )

    print()
    if fatal:
        print("  *** EXPORT REJECTED ***")
        for f in fatal:
            print(f"    - {f}")
        print("\n  Nothing was promoted. Serve the PyTorch checkpoint instead: a smaller")
        print("  model that predicts at chance is worth less than a larger one that works.")
        return 1

    print(f"  onnx fp32: OK (max|delta| {delta_fp32:.6f}, numerically identical)")
    if int8_bad:
        int8.unlink(missing_ok=True)
        print("  onnx int8: REJECTED and deleted --")
        for m in int8_bad:
            print(f"      {m}")
        print("      Serving fp32 instead: larger and slower, but faithful.")
    else:
        print(f"  onnx int8: OK (PR-AUC within {drop_int8:.4f}, rank correlation {rho_int8:.4f})")

    cal_src = ckpt / "calibration.json"
    if cal_src.exists():
        shutil.copyfile(cal_src, out_dir / "calibration.json")
        cal = Calibrator.load(cal_src)
        p = cal(s_i)
        print(f"\n  calibration carried across: {cal.method}, "
              f"served scores span {p.min():.3f}-{p.max():.3f}")
    else:
        print("\n  NOTE: no calibration.json beside the checkpoint. Served probabilities "
              "will be raw model output.")

    if args.promote:
        meta = read_run_meta(ckpt) or {}
        path = promote_checkpoint(ckpt, out_dir, note="promoted by ml.export_onnx after fidelity gate")
        print(f"\n[promote] {path}")
        print(f"          checkpoint {ckpt}")
        print(f"          onnx       {out_dir}")
        if meta.get("threshold") is not None:
            print(f"          threshold  {meta['threshold']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
