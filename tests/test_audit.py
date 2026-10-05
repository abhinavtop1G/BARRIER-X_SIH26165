"""The audit trail."""

from __future__ import annotations

import json
import logging

import pytest

from api import audit


class Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []
        self.setFormatter(audit.JsonFormatter())

    def emit(self, record):
        self.records.append(json.loads(self.format(record)))


@pytest.fixture
def caplines():
    handler = Capture()
    lg = logging.getLogger(audit.AUDIT)
    lg.addHandler(handler)
    lg.setLevel(logging.INFO)
    prev, lg.propagate = lg.propagate, False
    yield handler.records
    lg.removeHandler(handler)
    lg.propagate = prev


def _record(**kw):
    base = dict(
        narrative="worker struck by a suspended load during a lift",
        probability=0.73, threshold=0.30, band="HIGH", flagged=True,
        model={"checkpoint": "seed2", "fingerprint": "abc123", "calibration": "platt"},
        latency_ms=12.5,
    )
    base.update(kw)
    audit.prediction_record(**base)


def test_every_field_an_audit_needs_is_present(caplines):
    _record()
    r = caplines[-1]
    for key in ("ts", "level", "request_id", "event", "narrative_sha256",
                "narrative_chars", "sif_probability", "threshold", "band",
                "flagged", "flagging_rule", "latency_ms",
                "model_checkpoint", "model_fingerprint", "model_calibration"):
        assert key in r, f"audit record lost {key!r}"
    assert r["event"] == "prediction"


def test_the_decision_is_reconstructable_from_the_record(caplines):
    _record(probability=0.29, threshold=0.30, band="BORDERLINE", flagged=False)
    r = caplines[-1]
    assert (r["sif_probability"] >= r["threshold"]) == r["flagged"]


def test_narrative_is_hashed_not_stored_by_default(caplines, monkeypatch):
    monkeypatch.delenv("SIF_AUDIT_TEXT", raising=False)
    secret = "worker injured at the Duliajan wellsite, named individual involved"
    _record(narrative=secret)
    r = caplines[-1]
    assert "narrative" not in r, "narrative text must not be logged by default"
    assert r["narrative_sha256"] == audit.hash_text(secret)
    assert r["narrative_chars"] == len(secret)
    assert secret not in json.dumps(r)


def test_narrative_is_stored_when_explicitly_enabled(caplines, monkeypatch):
    monkeypatch.setenv("SIF_AUDIT_TEXT", "1")
    _record(narrative="explicit opt in")
    assert caplines[-1]["narrative"] == "explicit opt in"


def test_hash_identifies_the_input(caplines):
    """Same text, same hash: that is what lets an auditor prove which input"""
    assert audit.hash_text("abc") == audit.hash_text("abc")
    assert audit.hash_text("abc") != audit.hash_text("abd")


def test_records_are_one_json_object_per_line(caplines):
    _record()
    line = json.dumps(caplines[-1])
    assert "\n" not in line
    assert json.loads(line)["event"] == "prediction"


def test_request_id_is_carried_into_the_record(caplines):
    token = audit.request_id_var.set("trace-42")
    try:
        _record()
    finally:
        audit.request_id_var.reset(token)
    assert caplines[-1]["request_id"] == "trace-42"


def test_caller_is_recorded_when_known(caplines):
    _record(caller="key:abc123def456")
    assert caplines[-1]["caller"] == "key:abc123def456"


def test_model_fingerprint_is_stable_and_content_derived(tmp_path):
    a, b = tmp_path / "a.bin", tmp_path / "b.bin"
    a.write_bytes(b"weights-one" * 1000)
    b.write_bytes(b"weights-two" * 1000)
    assert audit.model_fingerprint(a) == audit.model_fingerprint(a)
    assert audit.model_fingerprint(a) != audit.model_fingerprint(b)
    assert audit.model_fingerprint(tmp_path / "missing.bin") == "unknown"


def test_fingerprint_distinguishes_truncation(tmp_path):
    """Size is mixed in, so a prefix of a file is not confused with the file."""
    full, short = tmp_path / "full.bin", tmp_path / "short.bin"
    data = b"x" * 100_000
    full.write_bytes(data)
    short.write_bytes(data[:50_000])
    assert audit.model_fingerprint(full) != audit.model_fingerprint(short)


def test_new_request_ids_are_unique():
    assert len({audit.new_request_id() for _ in range(1000)}) == 1000
