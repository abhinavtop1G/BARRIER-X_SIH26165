"""api/audit.py -- structured logging and the prediction audit trail"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar
from pathlib import Path

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

AUDIT = "avertx.audit"
ACCESS = "avertx.access"


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Structured from the start, because an audit log"""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
                  + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "request_id": request_id_var.get(),
            "message": record.getMessage(),
        }
        extra = getattr(record, "fields", None)
        if extra:
            payload.update(extra)
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure(level: str | None = None) -> None:
    """Idempotent: uvicorn reloads import this module more than once."""
    level = (level or os.getenv("SIF_LOG_LEVEL", "INFO")).upper()
    root = logging.getLogger()
    for h in list(root.handlers):
        if getattr(h, "_avertx", False):
            root.removeHandler(h)

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(JsonFormatter())
    stream._avertx = True  # type: ignore[attr-defined]
    root.addHandler(stream)
    root.setLevel(level)

    path = os.getenv("SIF_AUDIT_LOG")
    if path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(p, encoding="utf-8")
        fh.setFormatter(JsonFormatter())
        fh._avertx = True  # type: ignore[attr-defined]
        logging.getLogger(AUDIT).addHandler(fh)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True


def log(logger: str, message: str, level: int = logging.INFO, **fields) -> None:
    """Structured log line."""
    logging.getLogger(logger).log(level, message, extra={"fields": fields})


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def model_fingerprint(path: str | Path, max_bytes: int = 64 << 20) -> str:
    """Content hash of the served weights, so a stored score can be tied to the"""
    p = Path(path)
    if not p.exists():
        return "unknown"
    h = hashlib.sha256()
    h.update(str(p.stat().st_size).encode())
    with p.open("rb") as fh:
        read = 0
        while read < max_bytes and (chunk := fh.read(1 << 20)):
            h.update(chunk)
            read += len(chunk)
    return h.hexdigest()[:16]


def prediction_record(
    *,
    narrative: str,
    probability: float,
    threshold: float,
    band: str,
    flagged: bool,
    model: dict,
    latency_ms: float,
    rule: str = "threshold",
    caller: str | None = None,
    **extra,
) -> None:
    """One line per scored narrative. This is the audit trail."""
    fields = {
        "event": "prediction",
        "narrative_sha256": hash_text(narrative),
        "narrative_chars": len(narrative),
        "sif_probability": round(float(probability), 6),
        "threshold": round(float(threshold), 6),
        "band": band,
        "flagged": bool(flagged),
        "flagging_rule": rule,
        "latency_ms": round(latency_ms, 2),
        **{f"model_{k}": v for k, v in model.items()},
    }
    if caller:
        fields["caller"] = caller
    fields.update({k: v for k, v in extra.items() if v not in (None, [], "")})
    if os.getenv("SIF_AUDIT_TEXT", "0") == "1":
        fields["narrative"] = narrative
    log(AUDIT, "prediction", **fields)
