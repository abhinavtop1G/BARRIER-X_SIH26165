#!/usr/bin/env python3
"""ml/verify_onnx.py  --  does this ONNX model still behave like the checkpoint?"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.export_onnx import (  # noqa: E402
    FP32_MAX_DELTA,
    INT8_MAX_PR_AUC_DROP,
    MIN_SCORE_SPAN,
    onnx_scores,
    torch_scores,
)

ROOT = Path(__file__).resolve().parents[1]
TEST = ROOT / "data" / "splits" / "test.csv"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--onnx-dir", required=True)
    ap.add_argument("--max-length", type=int, default=256)
    ap.add_argument("--quantize", action="store_true", help="also make and check an int8 copy")
    args = ap.parse_args()

    ckpt, onnx_dir = Path(args.checkpoint), Path(args.onnx_dir)
    tok_dir = onnx_dir if (onnx_dir / "tokenizer.json").exists() else ckpt

    fp32 = onnx_dir / "model.onnx"
    if not fp32.exists():
        found = sorted(p for p in onnx_dir.glob("*.onnx") if "int8" not in p.name)
        if not found:
            raise SystemExit(f"No fp32 .onnx in {onnx_dir}. The export did not produce one.")
        fp32 = found[0]
    print(f"[onnx] {fp32}  {fp32.stat().st_size/1e6:.1f} MB")

    df = pd.read_csv(TEST)
    texts = df["narrative_text"].astype(str).tolist()
    y = (df["sif_potential"] == "Yes").astype(int).to_numpy()

    s_t = torch_scores(ckpt, texts, args.max_length)
    ref = average_precision_score(y, s_t)
    rows = [("pytorch fp32", s_t, float("nan"))]

    s_o, lat = onnx_scores(fp32, tok_dir, texts, args.max_length)
    rows.append(("onnx fp32", s_o, lat))

    int8_path = onnx_dir / "model.int8.onnx"
    if args.quantize and not int8_path.exists():
        from onnxruntime.quantization import QuantType, quantize_dynamic

        quantize_dynamic(str(fp32), str(int8_path), weight_type=QuantType.QInt8)
        print(f"[int8] {int8_path}  {int8_path.stat().st_size/1e6:.1f} MB")
    if int8_path.exists():
        s_q, lat_q = onnx_scores(int8_path, tok_dir, texts, args.max_length)
        rows.append(("onnx int8", s_q, lat_q))

    print(f"\nfidelity on the frozen test set ({len(texts)} rows):")
    for tag, s, lat in rows:
        print(f"  {tag:<14} PR-AUC={average_precision_score(y, s):.4f}  "
              f"ROC-AUC={roc_auc_score(y, s):.4f}  span={s.max()-s.min():.4f}  "
              f"max|delta|={np.abs(s - s_t).max():.6f}  latency={lat:.1f} ms/doc")

    print()
    failures: list[str] = []
    for tag, s, _ in rows[1:]:
        span = float(s.max() - s.min())
        drop = ref - average_precision_score(y, s)
        bad = []
        if span < MIN_SCORE_SPAN:
            bad.append(f"score span {span:.5f} across {len(texts)} narratives -- "
                       f"emitting a constant, dead not lossy")
        if roc_auc_score(y, s) < 0.55:
            bad.append(f"ROC-AUC {roc_auc_score(y, s):.4f} at or near chance")
        if tag == "onnx fp32" and float(np.abs(s - s_t).max()) > FP32_MAX_DELTA:
            bad.append(f"max|delta| {np.abs(s - s_t).max():.6f} > {FP32_MAX_DELTA}")
        if tag == "onnx int8" and drop > INT8_MAX_PR_AUC_DROP:
            bad.append(f"PR-AUC {drop:.4f} below PyTorch (limit {INT8_MAX_PR_AUC_DROP})")
        if bad:
            failures.append(f"{tag}: " + "; ".join(bad))
            print(f"  *** DO NOT SHIP {tag} ***")
            for b in bad:
                print(f"        {b}")
        else:
            print(f"  {tag}: OK (within {drop:.4f} PR-AUC of PyTorch)")

    if failures:
        print("\n  A correct fp32 export is numerically identical to PyTorch. A gap this")
        print("  large means the conversion is wrong, not that precision was lost.")
        print("  Ship the PyTorch checkpoint instead -- a smaller model that predicts")
        print("  at chance is worth less than a larger one that works.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
