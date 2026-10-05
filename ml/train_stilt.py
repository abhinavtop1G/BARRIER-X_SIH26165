#!/usr/bin/env python3
"""ml/train_stilt.py  --  stage 2b: supervised intermediate training on PHMSA"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    get_linear_schedule_with_warmup,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.artifacts import load_tokenizer  # noqa: E402
from ml.evaluation import evaluate, select_threshold  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "model_artifacts"
REPORTS = ROOT / "data" / "reports"
PHMSA = ROOT / "data" / "seed" / "phmsa_serious.csv"

TEXT = "narrative_text"
LABEL = "sif_potential"


class NarrativeDataset(Dataset):
    """Tokenised lazily. 73K rows at max_length padding would be 2.7 GB of"""

    def __init__(self, df: pd.DataFrame, tokenizer, max_length: int):
        self.texts = df[TEXT].astype(str).tolist()
        self.y = torch.tensor((df[LABEL] == "Yes").astype(int).to_numpy(), dtype=torch.long)
        self.tok = tokenizer
        self.max_length = max_length

    def __len__(self) -> int:
        return len(self.y)

    def __getitem__(self, i):
        return {"text": self.texts[i], "label": self.y[i]}

    def collate(self, batch):
        enc = self.tok([b["text"] for b in batch], truncation=True,
                       max_length=self.max_length, padding=True, return_tensors="pt")
        enc["labels"] = torch.stack([b["label"] for b in batch])
        return enc


@torch.no_grad()
def predict_scores(model, loader, device) -> np.ndarray:
    model.eval()
    out = []
    for batch in loader:
        batch.pop("labels", None)
        batch = {k: v.to(device) for k, v in batch.items()}
        with torch.amp.autocast("cuda", enabled=(device.type == "cuda")):
            logits = model(**batch).logits
        out.append(torch.softmax(logits.float(), dim=-1)[:, 1].cpu().numpy())
    model.train()
    return np.concatenate(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="microsoft/deberta-v3-small")
    ap.add_argument("--init-from", default=str(ART / "deberta-v3-small_adapted_15k"),
                    help="MLM-adapted encoder from stage 2")
    ap.add_argument("--data", default=str(PHMSA))
    ap.add_argument("--out", default="deberta_phmsa_stilt")
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--max-steps", type=int, default=0, help="0 = no cap")
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--grad-accum", type=int, default=1)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--head-lr", type=float, default=1e-3,
                    help="the classifier head starts from scratch and needs a much "
                         "larger step than the pretrained encoder")
    ap.add_argument("--max-length", type=int, default=192)
    ap.add_argument("--eval-every", type=int, default=500)
    ap.add_argument("--no-fp16", action="store_true")
    args = ap.parse_args()

    data_path = Path(args.data)
    if not data_path.exists():
        raise SystemExit(f"{data_path} not found. Run: python data/build_phmsa.py")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    fp16 = (device.type == "cuda") and not args.no_fp16
    source = args.init_from if args.init_from and Path(args.init_from).exists() else args.model
    if source != args.init_from:
        print(f"[warn] {args.init_from} not found -- falling back to stock {args.model}")
    print(f"[device] {device}  init-from={source}")

    tokenizer = load_tokenizer(source, args.init_from, args.model)
    model = AutoModelForSequenceClassification.from_pretrained(source, num_labels=2)
    model = model.float().to(device)

    df = pd.read_csv(data_path)
    tr, va = df[df.split == "train"], df[df.split == "validation"]
    print(f"[data] {len(tr):,} train / {len(va):,} validation  "
          f"(base rate {(tr[LABEL] == 'Yes').mean():.1%})")

    ds_tr, ds_va = (NarrativeDataset(x, tokenizer, args.max_length) for x in (tr, va))
    dl_tr = DataLoader(ds_tr, batch_size=args.batch_size, shuffle=True,
                       collate_fn=ds_tr.collate, drop_last=True, num_workers=2,
                       pin_memory=(device.type == "cuda"))
    dl_va = DataLoader(ds_va, batch_size=args.batch_size * 2, collate_fn=ds_va.collate)

    y_tr = ds_tr.y.numpy()
    counts = np.bincount(y_tr, minlength=2)
    weights = torch.tensor(len(y_tr) / (2.0 * np.clip(counts, 1, None)),
                           dtype=torch.float, device=device)
    loss_fn = nn.CrossEntropyLoss(weight=weights)
    print(f"[loss] class weights {weights.tolist()}")

    head_names = ("classifier", "pooler")
    head = [p for n, p in model.named_parameters() if any(h in n for h in head_names)]
    body = [p for n, p in model.named_parameters() if not any(h in n for h in head_names)]
    optim = torch.optim.AdamW(
        [{"params": body, "lr": args.lr}, {"params": head, "lr": args.head_lr}],
        weight_decay=0.01,
    )

    steps_per_epoch = len(dl_tr) // args.grad_accum
    total = steps_per_epoch * args.epochs
    if args.max_steps:
        total = min(total, args.max_steps)
    sched = get_linear_schedule_with_warmup(optim, int(0.06 * total), total)
    scaler = torch.amp.GradScaler("cuda", enabled=fp16)
    print(f"[train] {total:,} steps, batch {args.batch_size}x{args.grad_accum}, "
          f"encoder lr {args.lr:g}, head lr {args.head_lr:g}, fp16={fp16}\n")

    y_va = ds_va.y.numpy()
    best, best_state, history = -1.0, None, []
    step, running, t0, done = 0, 0.0, time.perf_counter(), False
    model.train()
    optim.zero_grad(set_to_none=True)

    for epoch in range(1, args.epochs + 1):
        if done:
            break
        for micro, batch in enumerate(dl_tr):
            labels = batch.pop("labels").to(device)
            batch = {k: v.to(device, non_blocking=True) for k, v in batch.items()}
            with torch.amp.autocast("cuda", enabled=fp16):
                loss = loss_fn(model(**batch).logits, labels) / args.grad_accum
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

            if step % args.eval_every == 0 or step == total:
                s_va = predict_scores(model, dl_va, device)
                from sklearn.metrics import average_precision_score

                prauc = average_precision_score(y_va, s_va)
                rate = step / (time.perf_counter() - t0)
                print(f"  step {step:>6,}/{total:,}  loss={running/args.eval_every:.4f}  "
                      f"PHMSA val PR-AUC={prauc:.4f}  {rate:.1f} it/s  "
                      f"ETA {(total-step)/max(rate,1e-9)/60:.0f} min")
                history.append({"step": step, "loss": round(running / args.eval_every, 4),
                                "val_pr_auc": round(float(prauc), 4)})
                running = 0.0
                if prauc > best:
                    best = prauc
                    best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}

            if step >= total:
                done = True
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    s_va = predict_scores(model, dl_va, device)
    thr, reason = select_threshold(y_va, s_va, 0.50)
    rep = evaluate("PHMSA serious-incident (intermediate task)", y_va, s_va, thr, reason)
    print("\n" + rep.pretty())

    out_dir = ART / args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(out_dir)
    tokenizer.save_pretrained(out_dir)

    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / f"stilt_{args.out}.json").write_text(json.dumps({
        "init_from": source,
        "data": str(data_path),
        "train_rows": len(tr),
        "validation_rows": len(va),
        "steps": total,
        "batch_size": args.batch_size * args.grad_accum,
        "encoder_lr": args.lr,
        "head_lr": args.head_lr,
        "best_val_pr_auc": round(float(best), 4),
        "report": rep.to_row(),
        "history": history,
    }, indent=2))

    print(f"\nwrote -> {out_dir}")
    print(f"wrote -> {REPORTS}/stilt_{args.out}.json")
    print(f"\nNext: python -m ml.train_deberta --init-from {out_dir} --seeds 3")


if __name__ == "__main__":
    main()
