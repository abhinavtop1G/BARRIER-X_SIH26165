"""ml/artifacts.py  --  checkpoints that describe themselves"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "model_artifacts"
SERVING = ART / "SERVING.json"

RUN_META = "run_meta.json"
CALIBRATION = "calibration.json"


class ModelUnavailable(RuntimeError):
    """No usable model on disk, or one that cannot be loaded."""


def load_tokenizer(*candidates):
    """First candidate that loads wins."""
    import os

    from transformers import AutoTokenizer

    errors = []
    for c in candidates:
        if not c:
            continue
        for offline in (False, True):
            prev = os.environ.get("HF_HUB_OFFLINE")
            if offline:
                os.environ["HF_HUB_OFFLINE"] = "1"
            try:
                return AutoTokenizer.from_pretrained(str(c))
            except Exception as exc:
                if offline:
                    errors.append(f"  {c}: {type(exc).__name__}: {str(exc)[:110]}")
            finally:
                if offline:
                    if prev is None:
                        os.environ.pop("HF_HUB_OFFLINE", None)
                    else:
                        os.environ["HF_HUB_OFFLINE"] = prev
    raise ModelUnavailable("Could not load a tokenizer from any of:\n" + "\n".join(errors))


DEFAULT_BAND_MARGIN = 0.15


def band_margin_for(threshold: float, cal_val_scores, default: float = DEFAULT_BAND_MARGIN,
                    floor: float = 0.02) -> float:
    """A band width the model can actually populate."""
    import numpy as _np

    s = _np.asarray(cal_val_scores, dtype=float)
    if s.size == 0:
        return default
    lo, hi = float(s.min()), float(s.max())
    room = min(hi - threshold, threshold - lo) / 2.0
    return float(min(default, max(floor, room)))


def write_run_meta(ckpt_dir: str | Path, **fields) -> Path:
    """Record what this checkpoint is and how it should be operated."""
    p = Path(ckpt_dir) / RUN_META
    p.parent.mkdir(parents=True, exist_ok=True)
    fields.setdefault("written_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    p.write_text(json.dumps(fields, indent=2))
    return p


def read_run_meta(ckpt_dir: str | Path) -> dict | None:
    p = Path(ckpt_dir) / RUN_META
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None


def _rel(p: Path) -> str:
    """Repo-relative where possible, so SERVING.json survives being moved."""
    p = Path(p).resolve()
    try:
        return p.relative_to(ROOT).as_posix()
    except ValueError:
        return str(p)


def promote(ckpt_dir: str | Path, onnx_dir: str | Path | None = None, note: str = "") -> Path:
    """Name the checkpoint that predict.py and the API should serve."""
    ckpt = Path(ckpt_dir).resolve()
    if not ckpt.exists():
        raise SystemExit(f"Cannot promote {ckpt}: does not exist")
    meta = read_run_meta(ckpt)
    payload = {
        "checkpoint": _rel(ckpt),
        "onnx_dir": _rel(Path(onnx_dir)) if onnx_dir else None,
        "calibration": _rel(ckpt / CALIBRATION) if (ckpt / CALIBRATION).exists() else None,
        "threshold": (meta or {}).get("threshold"),
        "threshold_reason": (meta or {}).get("threshold_reason"),
        "source": (meta or {}).get("source"),
        "metrics": (meta or {}).get("metrics"),
        "note": note,
        "promoted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    SERVING.parent.mkdir(parents=True, exist_ok=True)
    SERVING.write_text(json.dumps(payload, indent=2))
    return SERVING


def read_serving() -> dict | None:
    """Paths come back absolute, resolved against the repo root."""
    if not SERVING.exists():
        return None
    try:
        d = json.loads(SERVING.read_text())
    except Exception:
        return None
    for key in ("checkpoint", "onnx_dir", "calibration"):
        if d.get(key):
            p = Path(d[key])
            d[key] = str(p if p.is_absolute() else (ROOT / p))
    if not d.get("checkpoint") or not Path(d["checkpoint"]).exists():
        return None
    return d
