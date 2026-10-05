"""Shared fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _model_present() -> bool:
    try:
        from ml.artifacts import read_serving

        served = read_serving()
        if not served:
            return False
        onnx = served.get("onnx_dir")
        ckpt = Path(served["checkpoint"])
        return bool(ckpt.exists() and (
            (onnx and any(Path(onnx).glob("*.onnx"))) or (ckpt / "model.safetensors").exists()
        ))
    except Exception:
        return False


HAS_MODEL = _model_present()


def pytest_configure(config):
    config.addinivalue_line("markers", "model: requires the trained model on disk")


def pytest_collection_modifyitems(config, items):
    if HAS_MODEL:
        return
    skip = pytest.mark.skip(reason="no model on disk; run `python -m ml.fetch_model`")
    for item in items:
        if "model" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Set service env vars and clear anything left over from the real shell, so a"""
    def _set(**kw):
        for k in ("SIF_API_KEYS", "SIF_RATE_LIMIT", "SIF_RATE_BURST",
                  "SIF_THRESHOLD", "SIF_MODEL_DIR", "SIF_AUDIT_TEXT", "SIF_AUDIT_LOG",
                  "SIF_STORE_ENABLED", "SIF_STORE_TEXT", "SIF_STORE_DB",
                  "SIF_SITE_WINDOW_DAYS", "SIF_SITE_HALF_LIFE_DAYS",
                  "SIF_SITE_LINK_THRESHOLD"):
            monkeypatch.delenv(k, raising=False)
        monkeypatch.setenv("SIF_STORE_DB", str(tmp_path / "observations.db"))
        for k, v in kw.items():
            monkeypatch.setenv(k, str(v))
    return _set


@pytest.fixture
def make_client(env):
    """A TestClient whose lifespan runs *after* the env is set."""
    from fastapi.testclient import TestClient

    clients = []

    def _make(**kw):
        env(**kw)
        from api.main import app

        c = TestClient(app)
        c.__enter__()
        clients.append(c)
        return c

    yield _make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client):
    """Unauthenticated, effectively unlimited."""
    return make_client(SIF_RATE_LIMIT=0)


SEVERE = "H2S alarm sounded at the wellhead; two technicians were working without breathing apparatus and one collapsed."
TRIVIAL = "An employee spilled coffee in the site office kitchen and wiped it up."
