"""ml/calibration.py  --  turn a ranking into a probability"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

EPS = 1e-6


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    return np.log(p / (1 - p))


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -50, 50)))


def brier(y: np.ndarray, p: np.ndarray) -> float:
    return float(np.mean((np.asarray(p, dtype=float) - np.asarray(y, dtype=float)) ** 2))


def log_loss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(np.asarray(p, dtype=float), EPS, 1 - EPS)
    y = np.asarray(y, dtype=float)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def expected_calibration_error(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    """Mean gap between confidence and accuracy, weighted by bin population."""
    y, p = np.asarray(y, dtype=float), np.asarray(p, dtype=float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    idx = np.clip(np.digitize(p, edges[1:-1]), 0, bins - 1)
    ece = 0.0
    for b in range(bins):
        m = idx == b
        if m.any():
            ece += m.mean() * abs(p[m].mean() - y[m].mean())
    return float(ece)


def _fit_platt(y: np.ndarray, s: np.ndarray, l2: float = 1e-3,
               iters: int = 200) -> tuple[float, float]:
    """Logistic regression of the label on logit(score): p = sigmoid(a*z + b)."""
    z = _logit(s)
    y = np.asarray(y, dtype=float)

    def loss(a: float, b: float) -> float:
        p = np.clip(_sigmoid(a * z + b), EPS, 1 - EPS)
        nll = -np.sum(y * np.log(p) + (1 - y) * np.log(1 - p))
        return float(nll + 0.5 * l2 * a * a)

    a, b = 1.0, 0.0
    best = (a, b, loss(a, b))
    for _ in range(iters):
        p = _sigmoid(a * z + b)
        w = np.clip(p * (1 - p), 1e-9, None)
        r = p - y
        g = np.array([np.sum(r * z) + l2 * a, np.sum(r)])
        h = np.array([
            [np.sum(w * z * z) + l2, np.sum(w * z)],
            [np.sum(w * z),          np.sum(w) + 1e-9],
        ])
        try:
            step = np.linalg.solve(h, g)
        except np.linalg.LinAlgError:
            break
        if not np.all(np.isfinite(step)):
            break

        cur = loss(a, b)
        t, improved = 1.0, False
        for _ in range(40):
            na, nb = a - t * step[0], b - t * step[1]
            if np.isfinite(na) and np.isfinite(nb) and loss(na, nb) <= cur:
                a, b, improved = na, nb, True
                break
            t *= 0.5
        if not improved:
            break

        cand = loss(a, b)
        if cand < best[2]:
            best = (a, b, cand)
        if t * np.max(np.abs(step)) < 1e-10:
            break

    return float(best[0]), float(best[1])


def _fit_isotonic(y: np.ndarray, s: np.ndarray) -> tuple[list[float], list[float]]:
    """Pool-adjacent-violators. Non-parametric and monotonic, but it can place a"""
    order = np.argsort(s)
    xs, ys = np.asarray(s, dtype=float)[order], np.asarray(y, dtype=float)[order]
    vals, wts = list(ys), [1.0] * len(ys)
    i = 0
    while i < len(vals) - 1:
        if vals[i] <= vals[i + 1] + 1e-12:
            i += 1
            continue
        tot = wts[i] + wts[i + 1]
        vals[i] = (vals[i] * wts[i] + vals[i + 1] * wts[i + 1]) / tot
        wts[i] = tot
        del vals[i + 1], wts[i + 1]
        i = max(i - 1, 0)
    out: list[float] = []
    for v, w in zip(vals, wts):
        out.extend([v] * int(round(w)))
    out = (out + [out[-1]] * len(xs))[: len(xs)] if out else [float(ys.mean())] * len(xs)
    return [float(v) for v in xs], [float(v) for v in out]


@dataclass
class Calibrator:
    """A monotonic map from raw model score to calibrated probability."""

    method: str
    params: dict
    fitted_on: dict

    def __call__(self, s: np.ndarray) -> np.ndarray:
        s = np.asarray(s, dtype=float)
        if self.method == "platt":
            return _sigmoid(self.params["a"] * _logit(s) + self.params["b"])
        if self.method == "isotonic":
            return np.interp(s, self.params["x"], self.params["y"])
        return s

    @classmethod
    def fit(cls, y_val: np.ndarray, s_val: np.ndarray,
            method: str = "auto", min_rows_for_isotonic: int = 500) -> "Calibrator":
        """Fit on VALIDATION scores. Never pass test data to this."""
        y = np.asarray(y_val, dtype=float)
        s = np.asarray(s_val, dtype=float)

        cands: dict[str, Calibrator] = {
            "identity": cls("identity", {}, {}),
            "platt": cls("platt", dict(zip(("a", "b"), _fit_platt(y, s))), {}),
        }
        if len(y) >= min_rows_for_isotonic:
            x_i, y_i = _fit_isotonic(y, s)
            cands["isotonic"] = cls("isotonic", {"x": x_i, "y": y_i}, {})

        if method != "auto":
            if method not in cands:
                raise ValueError(f"method {method!r} unavailable (have {sorted(cands)})")
            best = method
        else:
            best = min(cands, key=lambda k: log_loss(y, cands[k](s)))

        chosen = cands[best]
        chosen.fitted_on = {
            "n": int(len(y)),
            "base_rate": round(float(y.mean()), 4),
            "raw_range": [round(float(s.min()), 4), round(float(s.max()), 4)],
            "raw_log_loss": round(log_loss(y, s), 4),
            "raw_brier": round(brier(y, s), 4),
            "raw_ece": round(expected_calibration_error(y, s), 4),
            "cal_log_loss": round(log_loss(y, chosen(s)), 4),
            "cal_brier": round(brier(y, chosen(s)), 4),
            "cal_ece": round(expected_calibration_error(y, chosen(s)), 4),
            "considered": {k: round(log_loss(y, v(s)), 4) for k, v in cands.items()},
        }
        return chosen

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(
            {"method": self.method, "params": self.params, "fitted_on": self.fitted_on},
            indent=2,
        ))

    @classmethod
    def load(cls, path: str | Path) -> "Calibrator":
        d = json.loads(Path(path).read_text())
        return cls(d["method"], d["params"], d.get("fitted_on", {}))

    @classmethod
    def identity(cls) -> "Calibrator":
        return cls("identity", {}, {})

    def summary(self) -> str:
        f = self.fitted_on
        if not f:
            return f"calibration: {self.method} (no provenance)"
        return (
            f"calibration: {self.method}  fitted on {f['n']} validation rows\n"
            f"    raw  range={f['raw_range']}  log-loss={f['raw_log_loss']:.4f}  "
            f"Brier={f['raw_brier']:.4f}  ECE={f['raw_ece']:.4f}\n"
            f"    cal  log-loss={f['cal_log_loss']:.4f}  "
            f"Brier={f['cal_brier']:.4f}  ECE={f['cal_ece']:.4f}"
        )


def _refit_cli() -> int:
    """Refit calibration.json from the raw validation scores saved beside a"""
    import argparse
    import glob

    ap = argparse.ArgumentParser(description=_refit_cli.__doc__)
    ap.add_argument("--refit", nargs="*", default=[], help="checkpoint dirs")
    ap.add_argument("--refit-all", action="store_true",
                    help="every checkpoint under model_artifacts/ with saved scores")
    ap.add_argument("--method", default="auto", choices=["auto", "platt", "isotonic", "identity"])
    args = ap.parse_args()

    targets = list(args.refit)
    if args.refit_all:
        root = Path(__file__).resolve().parents[1] / "model_artifacts"
        targets += [str(Path(p).parent) for p in glob.glob(str(root / "**" / "scores_val_raw.npy"),
                                                           recursive=True)]
    if not targets:
        ap.error("pass --refit <dir> or --refit-all")

    changed = 0
    for t in sorted(set(targets)):
        d = Path(t)
        sv, yv = d / "scores_val_raw.npy", d / "y_val.npy"
        if not (sv.exists() and yv.exists()):
            print(f"  [skip] {d}  (no saved validation scores)")
            continue
        s, y = np.load(sv), np.load(yv)
        old = Calibrator.load(d / "calibration.json") if (d / "calibration.json").exists() else None
        new = Calibrator.fit(y, s, method=args.method)
        before = old.method if old else "none"
        old_ll = old.fitted_on.get("cal_log_loss") if old and old.fitted_on else None
        note = ""
        if old_ll is not None and new.fitted_on["cal_log_loss"] < old_ll - 1e-9:
            note = f"  (val log-loss {old_ll:.4f} -> {new.fitted_on['cal_log_loss']:.4f})"
            changed += 1
        elif before != new.method:
            changed += 1
        new.save(d / "calibration.json")
        print(f"  {d.parent.name}/{d.name:<8} {before:>8} -> {new.method:<8}"
              f"  ECE {new.fitted_on['raw_ece']:.4f} -> {new.fitted_on['cal_ece']:.4f}{note}")
    print(f"\n  {changed} calibrator(s) improved or changed method")
    return 0


if __name__ == "__main__":
    raise SystemExit(_refit_cli())
