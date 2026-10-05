"""The HTTP contract."""

from __future__ import annotations

import pytest

from tests.conftest import SEVERE, TRIVIAL


def test_health_reports_readiness_and_posture(client):
    r = client.get("/health")
    assert r.status_code == 200
    h = r.json()
    for key in ("status", "model_backend", "model", "model_fingerprint", "calibration",
                "default_threshold", "band_margin", "model_ready",
                "auth_enabled", "rate_limit_per_min"):
        assert key in h, f"/health lost the {key!r} field"
    assert h["status"] in ("ok", "degraded")
    assert isinstance(h["auth_enabled"], bool)


def test_root_lists_endpoints(client):
    body = client.get("/").json()
    assert body["service"]
    assert "/score" in body["endpoints"]


def test_request_id_is_returned_and_echoed(client):
    r = client.get("/")
    assert r.headers.get("X-Request-ID")

    mine = "abc123traceid"
    r = client.get("/", headers={"X-Request-ID": mine})
    assert r.headers["X-Request-ID"] == mine, "an upstream trace id must survive"


@pytest.mark.parametrize("payload", [
    {},
    {"narrative": "short"},
    {"narrative": "x" * 9000},
    {"narrative": SEVERE, "threshold": 1.5},
    {"narrative": SEVERE, "threshold": -0.1},
])
def test_invalid_requests_are_rejected(client, payload):
    assert client.post("/score", json=payload).status_code == 422


def test_batch_rejects_empty_and_oversized(client):
    assert client.post("/score/batch", json={"narratives": []}).status_code == 422
    assert client.post("/score/batch",
                       json={"narratives": [SEVERE] * 501}).status_code == 422


def test_missing_model_degrades_instead_of_crashing(make_client):
    """Regression: a missing model used to kill startup outright."""
    c = make_client(SIF_MODEL_DIR="/nonexistent/checkpoint", SIF_RATE_LIMIT=0)

    h = c.get("/health").json()
    assert h["status"] == "degraded", "the service must come up and say it is unhealthy"
    assert h["model_ready"] is False
    assert "FAILED" in h["model_backend"], "the reason must be visible on /health"

    r = c.post("/score", json={"narrative": SEVERE})
    assert r.status_code == 503
    assert "not loaded" in r.json()["detail"].lower()


@pytest.mark.model
def test_score_returns_full_traceable_response(client):
    r = client.post("/score", json={"narrative": SEVERE})
    assert r.status_code == 200
    b = r.json()
    for key in ("narrative", "sif_probability", "threshold", "flagged", "band",
                "guidance", "model", "calibration", "model_fingerprint"):
        assert key in b, f"/score lost the {key!r} field"
    assert 0.0 <= b["sif_probability"] <= 1.0
    assert b["band"] in ("HIGH", "ELEVATED", "BORDERLINE", "LOW")
    assert b["flagged"] == (b["sif_probability"] >= b["threshold"])
    assert b["model_fingerprint"] not in ("", "unknown")


@pytest.mark.model
def test_band_agrees_with_threshold(client):
    b = client.post("/score", json={"narrative": SEVERE}).json()
    above = b["sif_probability"] >= b["threshold"]
    assert (b["band"] in ("HIGH", "ELEVATED")) == above


@pytest.mark.model
def test_threshold_override_changes_the_decision(client):
    assert client.post("/score", json={"narrative": TRIVIAL,
                                       "threshold": 0.0}).json()["flagged"] is True
    assert client.post("/score", json={"narrative": SEVERE,
                                       "threshold": 1.0}).json()["flagged"] is False


@pytest.mark.model
def test_severe_outranks_trivial(client):
    """The product is the ordering. If this fails, nothing else matters."""
    s = client.post("/score", json={"narrative": SEVERE}).json()["sif_probability"]
    t = client.post("/score", json={"narrative": TRIVIAL}).json()["sif_probability"]
    assert s > t, f"severe {s} did not outrank trivial {t}"


@pytest.mark.model
def test_batch_is_sorted_by_risk_and_counts_match(client):
    r = client.post("/score/batch", json={"narratives": [TRIVIAL, SEVERE, TRIVIAL]})
    assert r.status_code == 200
    b = r.json()
    assert b["count"] == 3 and len(b["results"]) == 3
    probs = [x["sif_probability"] for x in b["results"]]
    assert probs == sorted(probs, reverse=True), "queue order is the product"
    assert b["flagged_count"] == sum(x["flagged"] for x in b["results"])
    assert b["flagging_rule"]


@pytest.mark.model
def test_batch_unsorted_preserves_submission_order_with_duplicates(client):
    subs = [SEVERE, TRIVIAL, SEVERE, TRIVIAL]
    out = client.post("/score/batch", json={"narratives": subs, "sort": False}).json()
    assert [x["narrative"] for x in out["results"]] == subs


@pytest.mark.model
def test_top_frac_flags_by_rank_not_threshold(client):
    subs = [TRIVIAL] * 8 + [SEVERE, SEVERE]
    b = client.post("/score/batch",
                    json={"narratives": subs, "top_frac": 0.2}).json()
    assert b["flagged_count"] == 2, "top_frac must flag exactly the top slice"
    assert all(x["flagged"] for x in b["results"][:2])
    assert not any(x["flagged"] for x in b["results"][2:])
    assert "rank" in b["flagging_rule"]


@pytest.mark.model
def test_batch_and_single_agree(client):
    single = client.post("/score", json={"narrative": SEVERE}).json()["sif_probability"]
    batch = client.post("/score/batch",
                        json={"narratives": [SEVERE]}).json()["results"][0]["sif_probability"]
    assert single == batch, "the same text must score the same through either endpoint"
