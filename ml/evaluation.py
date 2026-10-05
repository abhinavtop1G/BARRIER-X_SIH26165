"""ml/evaluation.py  --  one evaluation harness, used by every model in ml/."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    precision_recall_curve,
    roc_auc_score,
)

DEFAULT_KS = (10, 20, 50)


def precision_at_k(y_true: np.ndarray, scores: np.ndarray, k: int) -> float:
    """Precision among the k highest-scored items -- the reviewer's top-of-queue."""
    k = min(k, len(scores))
    idx = np.argsort(-scores)[:k]
    return float(np.mean(y_true[idx]))


def lift_at_k(y_true: np.ndarray, scores: np.ndarray, k: int) -> float:
    """precision@k divided by the base rate. 1.0 == no better than random."""
    base = float(np.mean(y_true))
    return precision_at_k(y_true, scores, k) / base if base > 0 else float("nan")


def recall_at_k(y_true: np.ndarray, scores: np.ndarray, k: int) -> float:
    k = min(k, len(scores))
    idx = np.argsort(-scores)[:k]
    total = y_true.sum()
    return float(y_true[idx].sum() / total) if total else float("nan")


def select_threshold(
    y_val: np.ndarray, s_val: np.ndarray, precision_floor: float = 0.50
) -> tuple[float, str]:
    """Highest-recall threshold that still clears a precision floor on VALIDATION."""
    prec, rec, thr = precision_recall_curve(y_val, s_val)
    prec, rec = prec[:-1], rec[:-1]
    ok = prec >= precision_floor
    if ok.any():
        best = np.argmax(np.where(ok, rec, -1))
        return float(thr[best]), f"precision_floor>={precision_floor:.2f} met on validation"
    f1 = 2 * prec * rec / np.clip(prec + rec, 1e-12, None)
    best = int(np.argmax(f1))
    return float(thr[best]), f"precision floor {precision_floor:.2f} UNREACHABLE; fell back to max-F1"


@dataclass
class EvalReport:
    name: str
    n: int
    base_rate: float
    threshold: float
    threshold_reason: str
    precision: float
    recall: float
    f1: float
    pr_auc: float
    roc_auc: float
    brier: float
    confusion: dict[str, int]
    triage: dict[str, float] = field(default_factory=dict)

    def to_row(self) -> dict:
        d = {
            "model": self.name,
            "n_test": self.n,
            "base_rate": round(self.base_rate, 4),
            "threshold": round(self.threshold, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "pr_auc": round(self.pr_auc, 4),
            "roc_auc": round(self.roc_auc, 4),
            "brier": round(self.brier, 4),
        }
        d.update({k: round(v, 4) for k, v in self.triage.items()})
        return d

    def pretty(self) -> str:
        c = self.confusion
        lines = [
            f"=== {self.name} ===",
            f"  n={self.n}  base_rate={self.base_rate:.3f}",
            f"  threshold={self.threshold:.4f}  ({self.threshold_reason})",
            f"  precision={self.precision:.4f}  recall={self.recall:.4f}  F1={self.f1:.4f}",
            f"  PR-AUC={self.pr_auc:.4f}  ROC-AUC={self.roc_auc:.4f}  Brier={self.brier:.4f}",
            f"  TP={c['tp']} FP={c['fp']} TN={c['tn']} FN={c['fn']}",
            "  triage:  " + "  ".join(f"{k}={v:.3f}" for k, v in self.triage.items()),
        ]
        return "\n".join(lines)


def evaluate(
    name: str,
    y_true: np.ndarray,
    scores: np.ndarray,
    threshold: float,
    threshold_reason: str = "",
    ks: tuple[int, ...] = DEFAULT_KS,
) -> EvalReport:
    y_true = np.asarray(y_true).astype(int)
    scores = np.asarray(scores, dtype=float)
    pred = (scores >= threshold).astype(int)

    tp = int(((pred == 1) & (y_true == 1)).sum())
    fp = int(((pred == 1) & (y_true == 0)).sum())
    tn = int(((pred == 0) & (y_true == 0)).sum())
    fn = int(((pred == 0) & (y_true == 1)).sum())

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    triage: dict[str, float] = {}
    for k in ks:
        triage[f"P@{k}"] = precision_at_k(y_true, scores, k)
        triage[f"lift@{k}"] = lift_at_k(y_true, scores, k)
        triage[f"R@{k}"] = recall_at_k(y_true, scores, k)

    return EvalReport(
        name=name,
        n=len(y_true),
        base_rate=float(y_true.mean()),
        threshold=threshold,
        threshold_reason=threshold_reason,
        precision=precision,
        recall=recall,
        f1=f1,
        pr_auc=float(average_precision_score(y_true, scores)),
        roc_auc=float(roc_auc_score(y_true, scores)),
        brier=float(brier_score_loss(y_true, np.clip(scores, 0, 1))),
        confusion={"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        triage=triage,
    )
