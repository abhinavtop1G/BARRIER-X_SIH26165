#!/usr/bin/env python3
"""ml/train_deberta.py  --  stage 3: fine-tune a transformer for SIF classification"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, get_linear_schedule_with_warmup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ml.artifacts import ART, band_margin_for, load_tokenizer, write_run_meta  # noqa: E402
from ml.calibration import Calibrator  # noqa: E402
from ml.evaluation import evaluate, select_threshold  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "data" / "reports"

TEXT = "narrative_text"
LABEL = "sif_potential"


class NarrativeDataset(Dataset):
    def __init__(self, df: pd.DataFrame, tokenizer, max_length: int):
        self.enc = tokenizer(
            df[TEXT].astype(str).tolist(),
            truncation=True,
            max_length=max_length,
            padding="max_length",
            return_tensors="pt",
        )
        self.y = torch.tensor((df[LABEL] == "Yes").astype(int).to_numpy(), dtype=torch.long)

    def __len__(self) -> int:
        return len(self.y)

    def __getitem__(self, i):
        item = {k: v[i] for k, v in self.enc.items()}
        item["labels"] = self.y[i]
        return item


@torch.no_grad()
def predict_scores(model, loader, device) -> np.ndarray:
    model.eval()
    out = []
    for batch in loader:
        batch.pop("labels", None)
        batch = {k: v.to(device) for k, v in batch.items()}
        out.append(torch.softmax(model(**batch).logits.float(), dim=-1)[:, 1].cpu().numpy())
    return np.concatenate(out)


def head_body_groups(model, lr: float, head_lr: float):
    """Split parameters into pretrained encoder and task head."""
    names = ("classifier", "pooler")
    head = [p for n, p in model.named_parameters() if any(h in n for h in names)]
    body = [p for n, p in model.named_parameters() if not any(h in n for h in names)]
    return [{"params": body, "lr": lr}, {"params": head, "lr": head_lr}]


def train_one_seed(args, frames, seed: int, device, tokenizer, source: str,
                   run_tag: str) -> dict:
    torch.manual_seed(seed)
    np.random.seed(seed)

    model = AutoModelForSequenceClassification.from_pretrained(
        source, num_labels=2, id2label={0: "No", 1: "Yes"}, label2id={"No": 0, "Yes": 1}
    )
    if args.reset_head:
        std = model.config.initializer_range
        for mod in (model.classifier, getattr(model, "pooler", None)):
            if mod is None:
                continue
            for m in ([mod] if isinstance(mod, nn.Linear) else mod.modules()):
                if isinstance(m, nn.Linear):
                    m.weight.data.normal_(mean=0.0, std=std)
                    if m.bias is not None:
                        m.bias.data.zero_()
    model = model.float().to(device)

    sets = {k: NarrativeDataset(v, tokenizer, args.max_length) for k, v in frames.items()}
    loaders = {
        "train": DataLoader(sets["train"], batch_size=args.batch_size, shuffle=True),
        "validation": DataLoader(sets["validation"], batch_size=args.batch_size * 2),
        "test": DataLoader(sets["test"], batch_size=args.batch_size * 2),
    }

    y_train = sets["train"].y.numpy()
    counts = np.bincount(y_train, minlength=2)
    weights = torch.tensor(len(y_train) / (2.0 * np.clip(counts, 1, None)),
                           dtype=torch.float, device=device)
    loss_fn = nn.CrossEntropyLoss(weight=weights)

    head_lr = args.head_lr if args.head_lr else args.lr * args.head_lr_mult
    optim = torch.optim.AdamW(head_body_groups(model, args.lr, head_lr), weight_decay=0.01)
    total = max(1, len(loaders["train"]) // args.grad_accum) * args.epochs
    sched = get_linear_schedule_with_warmup(optim, int(0.1 * total), total)
    scaler = torch.amp.GradScaler("cuda", enabled=(device.type == "cuda" and args.fp16))

    y_val = sets["validation"].y.numpy()
    best_prauc, best_state, patience = -1.0, None, 0

    for epoch in range(1, args.epochs + 1):
        model.train()
        running = 0.0
        optim.zero_grad(set_to_none=True)
        for micro, batch in enumerate(loaders["train"]):
            labels = batch.pop("labels").to(device)
            batch = {k: v.to(device) for k, v in batch.items()}
            with torch.amp.autocast("cuda", enabled=(device.type == "cuda" and args.fp16)):
                loss = loss_fn(model(**batch).logits, labels) / args.grad_accum
            scaler.scale(loss).backward()
            running += loss.item() * args.grad_accum
            if (micro + 1) % args.grad_accum and (micro + 1) != len(loaders["train"]):
                continue
            scaler.unscale_(optim)
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            scaler.step(optim)
            scaler.update()
            sched.step()
            optim.zero_grad(set_to_none=True)

        s_val = predict_scores(model, loaders["validation"], device)
        from sklearn.metrics import average_precision_score

        prauc = average_precision_score(y_val, s_val)
        print(f"  seed {seed} epoch {epoch}: train_loss={running/len(loaders['train']):.4f}  "
              f"val_PR-AUC={prauc:.4f}")

        if prauc > best_prauc + 1e-4:
            best_prauc, patience = prauc, 0
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else:
            patience += 1
            if patience >= args.patience:
                print(f"  seed {seed}: early stop at epoch {epoch}")
                break

    if best_state is not None:
        model.load_state_dict(best_state)

    s_val = predict_scores(model, loaders["validation"], device)
    s_test = predict_scores(model, loaders["test"], device)
    y_test = sets["test"].y.numpy()

    cal = Calibrator.fit(y_val, s_val)
    thr_raw, reason = select_threshold(y_val, s_val, args.precision_floor)
    thr_cal = float(cal(np.array([thr_raw]))[0])

    tag = f"{run_tag} seed={seed}"
    rep = evaluate(tag, y_test, cal(s_test), thr_cal, reason)
    print(rep.pretty())
    print("  " + cal.summary().replace("\n", "\n  "))

    span_raw = float(s_test.max() - s_test.min())
    span_cal = float(cal(s_test).max() - cal(s_test).min())
    margin = band_margin_for(thr_cal, cal(s_val))
    print(f"  score span: raw {span_raw:.3f} -> calibrated {span_cal:.3f}")

    out = None
    if args.save_dir:
        out = ART / args.save_dir / f"seed{seed}"
        out.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(out)
        tokenizer.save_pretrained(out)
        cal.save(out / "calibration.json")
        np.save(out / "scores_val_raw.npy", s_val)
        np.save(out / "scores_test_raw.npy", s_test)
        np.save(out / "y_val.npy", y_val)
        write_run_meta(
            out,
            source=source,
            seed=seed,
            threshold=thr_cal,
            threshold_raw=thr_raw,
            threshold_reason=reason,
            band_margin=round(margin, 4),
            calibration=cal.method,
            max_length=args.max_length,
            encoder_lr=args.lr,
            head_lr=head_lr,
            reset_head=bool(args.reset_head),
            epochs_run=epoch,
            best_val_pr_auc=round(float(best_prauc), 4),
            raw_score_span=round(span_raw, 4),
            calibrated_score_span=round(span_cal, 4),
            metrics=rep.to_row(),
        )

    return {"report": rep, "scores_test": s_test, "scores_val": s_val,
            "y_val": y_val, "y_test": y_test, "calibrator": cal, "dir": out}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="microsoft/deberta-v3-small")
    ap.add_argument("--init-from", default=None,
                    help="stage-2 (MLM) or stage-2b (STILT) checkpoint")
    ap.add_argument("--epochs", type=int, default=15)
    ap.add_argument("--batch-size", type=int, default=8)
    ap.add_argument("--grad-accum", type=int, default=1,
                    help="effective batch = batch_size * this; raise if you hit OOM")
    ap.add_argument("--lr", type=float, default=3e-5, help="encoder learning rate")
    ap.add_argument("--head-lr", type=float, default=None,
                    help="classifier head lr (default: lr * --head-lr-mult)")
    ap.add_argument("--head-lr-mult", type=float, default=20.0,
                    help="head lr as a multiple of encoder lr. The head is random at "
                         "init and 29 steps/epoch at 3e-5 barely moves it.")
    ap.add_argument("--max-length", type=int, default=256)
    ap.add_argument("--patience", type=int, default=5)
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--precision-floor", type=float, default=0.50)
    ap.add_argument("--fp16", action="store_true", default=True)
    ap.add_argument("--save-dir", default=None,
                    help="default: deberta_sif/<run name>, so runs do not overwrite "
                         "each other")
    ap.add_argument("--reset-head", action="store_true",
                    help="re-initialise the classifier head, keeping only the encoder. "
                         "Use with a STILT checkpoint, whose head is fitted to the "
                         "intermediate task's label distribution rather than ours.")
    ap.add_argument("--run-name", default=None,
                    help="names both the checkpoint dir and the report files. Defaults "
                         "to the source name. Set it when varying a hyperparameter on "
                         "the same encoder, or the second run overwrites the first.")
    args = ap.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    source = args.init_from or args.model
    tag = args.run_name or Path(source).name
    if args.save_dir is None:
        args.save_dir = str(Path("deberta_sif") / tag)
    print(f"[device] {device}  model={source}")
    print(f"[out]    {ART / args.save_dir}")

    tokenizer = load_tokenizer(source, args.model)

    frames = {
        name: pd.read_csv(ROOT / "data" / "splits" / f"{name}.csv")
        for name in ("train", "validation", "test")
    }

    runs = [train_one_seed(args, frames, s, device, tokenizer, source, tag)
            for s in range(args.seeds)]
    rows = [r["report"].to_row() for r in runs]

    ens_val = np.mean([r["calibrator"](r["scores_val"]) for r in runs], axis=0)
    ens_test = np.mean([r["calibrator"](r["scores_test"]) for r in runs], axis=0)
    y_val, y_test = runs[0]["y_val"], runs[0]["y_test"]
    thr, reason = select_threshold(y_val, ens_val, args.precision_floor)
    ens = evaluate(f"{tag} ENSEMBLE({args.seeds})", y_test, ens_test, thr, reason)
    print("\n" + ens.pretty())
    rows.append(ens.to_row())

    df = pd.DataFrame(rows)
    num = df.select_dtypes("number")
    print("\nper-seed mean +/- std:")
    for col in ("precision", "recall", "f1", "pr_auc", "roc_auc", "brier", "P@10", "P@20"):
        if col in num:
            vals = num[col].iloc[: args.seeds]
            print(f"  {col:<10} {vals.mean():.4f} +/- {vals.std():.4f}")

    REPORTS.mkdir(parents=True, exist_ok=True)
    df.to_csv(REPORTS / f"deberta_{tag}.csv", index=False)
    np.save(REPORTS / f"deberta_{tag}_test_scores.npy", ens_test)
    (REPORTS / f"deberta_{tag}.json").write_text(json.dumps(rows, indent=2))
    print(f"\nwrote -> {REPORTS}/deberta_{tag}.*")
    print(f"wrote -> {ART / args.save_dir}/seed*/  (weights, calibration.json, run_meta.json)")


if __name__ == "__main__":
    main()
