#!/usr/bin/env python3
"""ml/preflight.py  --  run this FIRST tomorrow. Takes 30 seconds."""

from __future__ import annotations

import importlib
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

OK, WARN, FAIL = "[ OK ]", "[WARN]", "[FAIL]"
problems: list[str] = []


def check(label: str, ok: bool, detail: str = "", fatal: bool = True,
          ok_detail: str = "") -> bool:
    """detail is the remediation hint, shown only on failure."""
    tag = OK if ok else (FAIL if fatal else WARN)
    shown = ok_detail if ok else detail
    print(f"{tag} {label}" + (f" -- {shown}" if shown else ""))
    if not ok and fatal:
        problems.append(label)
    return ok


def main() -> None:
    print("=" * 66)
    print("BARRIER X preflight")
    print("=" * 66)

    print("\nPackages")
    for mod, hint in [
        ("torch", "pip install torch"),
        ("transformers", "pip install transformers"),
        ("sentencepiece", "pip install sentencepiece  <- DeBERTa tokenizer needs this"),
        ("sklearn", "pip install scikit-learn"),
        ("pandas", "pip install pandas"),
        ("optimum", "pip install optimum[onnxruntime]  <- the ONLY safe DeBERTa ONNX export"),
        ("onnxruntime", "pip install onnxruntime"),
    ]:
        try:
            m = importlib.import_module(mod)
            check(mod, True, ok_detail=getattr(m, "__version__", ""))
        except ImportError:
            check(mod, False, hint)
        except Exception as exc:
            check(mod, False, f"INSTALLED BUT BROKEN: {type(exc).__name__}. "
                              f"Reinstall it: pip uninstall {mod} && {hint}")

    print("\nGPU")
    vram = 0.0
    try:
        import torch

        if check("CUDA available", torch.cuda.is_available(),
                 "" if torch.cuda.is_available() else "torch sees no GPU -- reinstall the CUDA build"):
            vram = torch.cuda.get_device_properties(0).total_memory / 1e9
            print(f"       {torch.cuda.get_device_name(0)}  {vram:.1f} GB VRAM")
    except Exception:
        check("CUDA available", False, "torch unusable -- fix the package errors above")

    print("\nData")
    corpus = ROOT / "data" / "mlm_corpus.txt"
    if check("MLM corpus", corpus.exists(), "run: python ml/build_mlm_corpus.py"):
        lines = sum(1 for _ in corpus.open(encoding="utf-8"))
        print(f"       {lines:,} narratives, {corpus.stat().st_size/1e6:.1f} MB")
        if lines < 50_000:
            print(f"{WARN} corpus is small ({lines:,}) -- adaptation gain will be limited")

    check("seed_labeled.csv", (ROOT / "data" / "seed" / "seed_labeled.csv").exists(),
          "run: python data/build_seed.py  (needs the Kaggle IHM file in data/raw/)")
    for name in ("train", "validation", "test"):
        p = ROOT / "data" / "splits" / f"{name}.csv"
        check(f"splits/{name}.csv", p.exists(), "run: python ml/build_splits.py --write")

    phmsa = ROOT / "data" / "seed" / "phmsa_serious.csv"
    if check("phmsa_serious.csv", phmsa.exists(),
             "run: python data/build_phmsa.py  (intermediate task, stage 2b)", fatal=False):
        import pandas as pd

        n = sum(1 for _ in phmsa.open(encoding="utf-8")) - 1
        print(f"       {n:,} labelled rows for supervised intermediate training")

    art = ROOT / "model_artifacts"
    if art.exists():
        print("\nCheckpoints")
        bad = []
        for cfg in sorted(art.rglob("tokenizer_config.json")):
            try:
                import json as _json

                if isinstance(_json.loads(cfg.read_text()).get("extra_special_tokens"), list):
                    bad.append(cfg.parent.relative_to(art))
            except Exception:
                pass
        check("tokenizer configs loadable", not bad,
              f"{len(bad)} checkpoint(s) unloadable on this transformers version. "
              f"Run: python -m ml.repair_checkpoints", fatal=False,
              ok_detail="all portable across transformers versions")
        for b in bad:
            print(f"       broken: {b}")

    print("\nDisk")
    free_gb = shutil.disk_usage(ROOT).free / 1e9
    check("free space", free_gb > 10, f"only {free_gb:.1f} GB free -- checkpoints need ~5 GB",
      fatal=False, ok_detail=f"{free_gb:.1f} GB free")

    print("\n" + "=" * 66)
    if problems:
        print("NOT READY. Fix these first:")
        for p in problems:
            print(f"  - {p}")
        return

    print("READY. Run in this order:\n")
    if vram >= 16:
        bs, ga, model = 32, 1, "microsoft/deberta-v3-base"
    elif vram >= 10:
        bs, ga, model = 16, 2, "microsoft/deberta-v3-base"
    elif vram > 0:
        bs, ga, model = 8, 4, "microsoft/deberta-v3-small"
    else:
        bs, ga, model = 8, 4, "microsoft/deberta-v3-small"

    tag = model.split("/")[-1]
    adapted = f"model_artifacts/{tag}_adapted"
    print(f"  # 0. Cheap controls first. Seconds, CPU. Includes the PHMSA controls")
    print(f"  #    that keep step 3 honest.")
    print(f"  python -m ml.baseline_tfidf\n")
    print(f"  # 1. CONTROL -- fine-tune with no adaptation. ~15-30 min.")
    print(f"  #    Do this first, so steps 2-3 have something to be measured against.")
    print(f"  python -m ml.train_deberta --model {model} --seeds 3\n")
    print(f"  # 2. Stage 2: MLM domain adaptation. Overnight.")
    print(f"  python -m ml.domain_adapt_mlm --model {model} \\")
    print(f"      --steps 20000 --batch-size {bs} --grad-accum {ga}\n")
    print(f"  # 2b. Stage 2b: supervised intermediate task on PHMSA. ~20 min.")
    print(f"  python data/build_phmsa.py")
    print(f"  python -m ml.train_stilt --init-from {adapted}\n")
    print(f"  # 3. Fine-tune each encoder on the 231 SIF rows. ~5 min each.")
    print(f"  python -m ml.train_deberta --init-from {adapted} --seeds 3")
    print(f"  python -m ml.train_deberta --init-from model_artifacts/deberta_phmsa_stilt --seeds 3\n")
    print(f"  # 4. Export the winner, gated on fidelity, and mark it for serving.")
    print(f"  python -m ml.export_onnx \\")
    print(f"      --checkpoint model_artifacts/deberta_sif/<winning tag>/seed0 --promote\n")
    print(f"  Result = step 3 minus step 1. Those deltas are the experiment.")
    print(f"  Never report a single seed, and never re-draw the frozen test set.")
    print("=" * 66)


if __name__ == "__main__":
    main()
