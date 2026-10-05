#!/usr/bin/env python3
"""ml/domain_adapt_mlm.py  --  stage 2: teach the encoder safety vocabulary"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import torch
from torch.utils.data import DataLoader, Dataset
from transformers import (
    AutoModelForMaskedLM,
    AutoTokenizer,
    DataCollatorForLanguageModeling,
    get_linear_schedule_with_warmup,
)

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "model_artifacts"
CORPUS = ROOT / "data" / "mlm_corpus.txt"
REPORTS = ROOT / "data" / "reports"


class TextFileDataset(Dataset):
    """One narrative per line. Held-out rows were already removed by"""

    def __init__(self, path: Path, tokenizer, max_length: int, limit: int | None):
        self.lines = []
        with path.open(encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if limit and i >= limit:
                    break
                line = line.strip()
                if line:
                    self.lines.append(line)
        self.tok = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.lines)

    def __getitem__(self, i):
        enc = self.tok(
            self.lines[i],
            truncation=True,
            max_length=self.max_length,
            padding="max_length",
            return_tensors="pt",
        )
        return {k: v.squeeze(0) for k, v in enc.items()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="microsoft/deberta-v3-base")
    ap.add_argument("--out", default=None, help="default: deberta_domain_adapted / <model>_adapted")
    ap.add_argument("--corpus", default=str(CORPUS))
    ap.add_argument("--steps", type=int, default=20000)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--grad-accum", type=int, default=2, help="effective batch = batch_size * this")
    ap.add_argument("--lr", type=float, default=5e-5)
    ap.add_argument("--max-length", type=int, default=192)
    ap.add_argument("--mlm-probability", type=float, default=0.15)
    ap.add_argument("--limit", type=int, default=None, help="cap corpus lines (for a quick smoke run)")
    ap.add_argument("--save-every", type=int, default=5000)
    ap.add_argument("--no-fp16", action="store_true")
    args = ap.parse_args()

    corpus_path = Path(args.corpus)
    if not corpus_path.exists():
        raise SystemExit(f"{corpus_path} not found. Run: python ml/build_mlm_corpus.py")

    out_dir = ART / (args.out or f"{args.model.split('/')[-1]}_adapted")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    fp16 = (device.type == "cuda") and not args.no_fp16

    if device.type == "cuda":
        vram = torch.cuda.get_device_properties(0).total_memory / 1e9
        print(f"[gpu] {torch.cuda.get_device_name(0)}  {vram:.1f} GB")
        if vram < 10 and args.batch_size > 8:
            print(f"[gpu] under 10GB detected -- consider --batch-size 8 --grad-accum 4")
    else:
        print("[gpu] NO GPU FOUND. This will take days on CPU. Stop and check your torch install.")

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForMaskedLM.from_pretrained(args.model)
    model = model.float().to(device)
    print(f"[model] {args.model}  {sum(p.numel() for p in model.parameters())/1e6:.0f}M params")

    ds = TextFileDataset(corpus_path, tokenizer, args.max_length, args.limit)
    print(f"[corpus] {len(ds):,} narratives from {corpus_path.name}")

    loader = DataLoader(
        ds,
        batch_size=args.batch_size,
        shuffle=True,
        drop_last=True,
        collate_fn=DataCollatorForLanguageModeling(
            tokenizer=tokenizer, mlm=True, mlm_probability=args.mlm_probability
        ),
        num_workers=2,
        pin_memory=(device.type == "cuda"),
    )

    optim = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=0.01)
    sched = get_linear_schedule_with_warmup(optim, int(0.06 * args.steps), args.steps)
    scaler = torch.amp.GradScaler("cuda", enabled=fp16)

    eff = args.batch_size * args.grad_accum
    print(f"[train] {args.steps:,} steps, effective batch {eff}, fp16={fp16}\n")

    model.train()
    history, step, running, t0 = [], 0, 0.0, time.perf_counter()
    optim.zero_grad(set_to_none=True)

    while step < args.steps:
        for micro, batch in enumerate(loader):
            batch = {k: v.to(device, non_blocking=True) for k, v in batch.items()}
            with torch.amp.autocast("cuda", enabled=fp16):
                loss = model(**batch).loss / args.grad_accum
            scaler.scale(loss).backward()
            running += loss.item() * args.grad_accum

            if (micro + 1) % args.grad_accum:
                continue

            scaler.unscale_(optim)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(optim)
            scaler.update()
            sched.step()
            optim.zero_grad(set_to_none=True)
            step += 1

            if step % 200 == 0:
                avg = running / (200 * args.grad_accum)
                rate = step / (time.perf_counter() - t0)
                eta = (args.steps - step) / max(rate, 1e-9) / 60
                print(
                    f"  step {step:>6,}/{args.steps:,}  loss={avg:.4f}  "
                    f"ppl={math.exp(min(avg, 20)):>7.2f}  {rate:.2f} it/s  ETA {eta:.0f} min"
                )
                history.append({"step": step, "loss": round(avg, 4)})
                running = 0.0

            if args.save_every and step % args.save_every == 0:
                model.save_pretrained(out_dir)
                tokenizer.save_pretrained(out_dir)
                print(f"  [checkpoint] {out_dir}")

            if step >= args.steps:
                break

    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"mlm_{out_dir.name}.json").write_text(
        json.dumps(
            {
                "base_model": args.model,
                "corpus": str(corpus_path),
                "corpus_lines": len(ds),
                "steps": args.steps,
                "effective_batch": eff,
                "lr": args.lr,
                "max_length": args.max_length,
                "loss_history": history,
                "first_loss": history[0]["loss"] if history else None,
                "final_loss": history[-1]["loss"] if history else None,
            },
            indent=2,
        )
    )

    if len(history) >= 2:
        drop = history[0]["loss"] - history[-1]["loss"]
        print(f"\n[result] loss {history[0]['loss']:.4f} -> {history[-1]['loss']:.4f}  (drop {drop:.4f})")
        if drop < 0.1:
            print("[warn] loss barely moved. Adaptation probably did nothing --")
            print("       try --model roberta-base, or a higher --lr.")

    print(f"\nwrote -> {out_dir}")
    print(f"Next:  python ml/train_deberta.py --init-from {out_dir} --seeds 3")


if __name__ == "__main__":
    main()
