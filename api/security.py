"""api/security.py -- API key authentication and rate limiting"""

from __future__ import annotations

import hashlib
import os
import threading
import time

from fastapi import HTTPException, Request

EXEMPT_PATHS = {"/health", "/", "/docs", "/openapi.json", "/redoc", "/dashboard"}


def _keys() -> set[str]:
    raw = os.getenv("SIF_API_KEYS", "")
    return {hashlib.sha256(k.strip().encode()).hexdigest()
            for k in raw.split(",") if k.strip()}


def auth_enabled() -> bool:
    return bool(_keys())


def key_id(presented: str) -> str:
    """A short, stable, non-reversible label for logs. Never log the key."""
    return hashlib.sha256(presented.encode()).hexdigest()[:12]


def _presented(request: Request) -> str | None:
    header = request.headers.get("x-api-key")
    if header:
        return header.strip()
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def authenticate(request: Request) -> str:
    """Return a caller label. Raises 401 when auth is on and the key is bad."""
    if not auth_enabled():
        return f"anon:{request.client.host if request.client else 'unknown'}"

    presented = _presented(request)
    if not presented:
        raise HTTPException(
            status_code=401,
            detail="Missing API key. Send X-API-Key or Authorization: Bearer <key>.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if hashlib.sha256(presented.encode()).hexdigest() not in _keys():
        raise HTTPException(status_code=401, detail="Invalid API key.",
                            headers={"WWW-Authenticate": "Bearer"})
    return f"key:{key_id(presented)}"


class TokenBucket:
    """Per-caller token bucket."""

    def __init__(self, rate_per_min: float, burst: float):
        self.rate = rate_per_min / 60.0
        self.burst = max(burst, 1.0)
        self._state: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def take(self, caller: str, now: float | None = None) -> tuple[bool, float]:
        """(allowed, seconds until a token is available)."""
        now = now if now is not None else time.monotonic()
        with self._lock:
            tokens, last = self._state.get(caller, (self.burst, now))
            tokens = min(self.burst, tokens + (now - last) * self.rate)
            if tokens >= 1.0:
                self._state[caller] = (tokens - 1.0, now)
                return True, 0.0
            self._state[caller] = (tokens, now)
            return False, (1.0 - tokens) / self.rate if self.rate > 0 else 60.0

    def reset(self) -> None:
        with self._lock:
            self._state.clear()


def build_limiter() -> TokenBucket | None:
    rate = float(os.getenv("SIF_RATE_LIMIT", "60"))
    if rate <= 0:
        return None
    burst = float(os.getenv("SIF_RATE_BURST", "20"))
    return TokenBucket(rate, burst)


def enforce(limiter: TokenBucket | None, caller: str) -> None:
    if limiter is None:
        return
    ok, wait = limiter.take(caller)
    if not ok:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded.",
            headers={"Retry-After": str(max(1, int(wait + 0.999)))},
        )
