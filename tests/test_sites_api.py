"""The site-level HTTP contract."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ml.store import Store
from tests.conftest import SEVERE, TRIVIAL

HEIGHT_A = ("A scaffold plank on the north platform moved underfoot as a fitter "
            "stepped onto it at about 8 metres.")
HEIGHT_B = ("Fitter working at height on the same platform had his harness lanyard "
            "clipped to the scaffold tube rather than the anchor point.")
HOTWORK = ("Gas detector at the welding bay was three weeks out of calibration; hot "
           "work was stopped and the unit swapped.")
PERMIT = ("Crew began breaking the flange on the test line before the permit to work "
          "had come back signed.")

SEEDED = [
    (HEIGHT_A, 0.45, 9, ["working_at_height"]),
    (HEIGHT_B, 0.42, 4, ["working_at_height"]),
    (HOTWORK, 0.38, 11, ["hot_work"]),
    (PERMIT, 0.36, 2, ["work_authorisation"]),
]


@pytest.fixture
def seeded(tmp_path):
    """A store with one accumulating site and one quiet one."""
    db = tmp_path / "observations.db"
    now = datetime.now(timezone.utc)
    with Store(db) as s:
        for text, p, days, rules in SEEDED:
            s.record("duliajan-rig-7", text, p, timestamp=now - timedelta(days=days),
                     rules=rules)
        s.record("moran-cpf", "Printer in the HSE office ran out of toner.", 0.12,
                 timestamp=now - timedelta(days=6))
    return db


@pytest.fixture
def site_client(make_client, seeded):
    return make_client(SIF_RATE_LIMIT=0, SIF_STORE_DB=str(seeded), SIF_THRESHOLD=0.5)


def test_health_reports_store_posture(client):
    h = client.get("/health").json()
    assert "store_enabled" in h and "store_status" in h
    assert h["store_enabled"] is True
    assert isinstance(h["store_status"], str) and h["store_status"]


def test_health_says_when_the_store_is_off(make_client):
    h = make_client(SIF_RATE_LIMIT=0, SIF_STORE_ENABLED=0).get("/health").json()
    assert h["store_enabled"] is False
    assert "SIF_STORE_ENABLED" in h["store_status"]


def test_root_advertises_the_site_endpoints(client):
    assert "/sites" in client.get("/").json()["endpoints"]


def test_sites_ranks_by_risk(site_client):
    b = site_client.get("/sites").json()
    assert b["count"] == 2
    risks = [s["site_risk"] for s in b["sites"]]
    assert risks == sorted(risks, reverse=True), "queue order is the product"
    assert b["sites"][0]["site_id"] == "duliajan-rig-7"


def test_sites_surfaces_the_compounding_case(site_client):
    """The reason the endpoint exists: nothing individual crossed 0.50."""
    top = site_client.get("/sites").json()["sites"][0]
    assert max(p for _, p, _, _ in SEEDED) < 0.5
    assert top["site_risk"] >= 0.5
    assert top["compounding"] is True
    assert top["escalation"] > 0


def test_quiet_site_does_not_alert(site_client):
    quiet = [s for s in site_client.get("/sites").json()["sites"]
             if s["site_id"] == "moran-cpf"][0]
    assert quiet["compounding"] is False
    assert quiet["level"] == "NORMAL"


def test_alerting_only_narrows_the_list_but_not_the_count(site_client):
    b = site_client.get("/sites", params={"alerting_only": True}).json()
    assert [s["site_id"] for s in b["sites"]] == ["duliajan-rig-7"]
    assert b["count"] == 1
    assert b["alerting_count"] == 1, "the count is of all alerting sites, not of the page"


def test_queue_rows_carry_their_hazards(site_client):
    top = site_client.get("/sites").json()["sites"][0]
    assert top["n_observations"] == 4
    assert top["n_clusters"] == 3
    assert "Working at Height" in top["top_hazards"]


def test_queue_states_the_threshold_it_judged_against(site_client):
    b = site_client.get("/sites").json()
    assert b["review_threshold"] == 0.5
    assert b["window_days"] == 90.0
    assert "not a measured probability" in b["caveat"]


def test_site_risk_uses_the_served_threshold_not_the_default(make_client, seeded):
    """`compounding` means "clears the bar the reviewer works to", so the bar has"""
    c = make_client(SIF_RATE_LIMIT=0, SIF_STORE_DB=str(seeded), SIF_THRESHOLD=0.3)
    b = c.get("/sites").json()
    assert b["review_threshold"] == 0.3
    assert b["sites"][0]["compounding"] is False


def test_site_detail_explains_itself(site_client):
    d = site_client.get("/sites/duliajan-rig-7").json()
    assert d["site_id"] == "duliajan-rig-7"
    assert len(d["clusters"]) == 3
    assert "COMPOUNDING" in d["explanation"]
    assert "Working at Height" in d["explanation"]


def test_site_detail_carries_its_evidence(site_client):
    d = site_client.get("/sites/duliajan-rig-7").json()
    height = [c for c in d["clusters"] if c["label"] == "Working at Height"][0]
    assert height["size"] == 2
    assert len(height["members"]) == 2
    assert height["recurrence_bonus"] > 0
    assert all(m["obs_id"] and m["timestamp"] for m in height["members"])
    assert any("scaffold plank" in m["narrative"] for m in height["members"])


def test_site_detail_records_the_params_it_used(site_client):
    p = site_client.get("/sites/duliajan-rig-7").json()["params"]
    for key in ("window_days", "half_life_days", "link_threshold",
                "recurrence_gain", "review_threshold", "max_clusters"):
        assert key in p, f"an assessment cannot be re-derived without {key!r}"


def test_clusters_sum_to_the_headline_by_noisy_or(site_client):
    """The explanation has to be checkable by hand, so verify it actually is."""
    d = site_client.get("/sites/duliajan-rig-7").json()
    survive = 1.0
    for c in d["clusters"]:
        if c["strength"] >= d["params"]["min_cluster_strength"]:
            survive *= (1 - c["strength"])
    assert 1 - survive == pytest.approx(d["site_risk"], abs=1e-3)


def test_unknown_site_is_404_not_an_empty_assessment(site_client):
    r = site_client.get("/sites/no-such-place")
    assert r.status_code == 404
    assert "no-such-place" in r.json()["detail"]


def test_sites_is_503_with_a_reason_when_the_store_is_off(make_client):
    c = make_client(SIF_RATE_LIMIT=0, SIF_STORE_ENABLED=0)
    for path in ("/sites", "/sites/anywhere"):
        r = c.get(path)
        assert r.status_code == 503, f"{path} should report unavailable, not 404"
        assert "unavailable" in r.json()["detail"].lower()


@pytest.mark.model
def test_scoring_survives_a_store_that_cannot_be_written(make_client, tmp_path):
    """A broken store must cost the history, never the score."""
    blocked = tmp_path / "afile"
    blocked.write_text("not a directory")
    c = make_client(SIF_RATE_LIMIT=0, SIF_STORE_DB=str(blocked / "nested" / "obs.db"))

    r = c.post("/score", json={"narrative": SEVERE, "site_id": "rig-7"})
    assert r.status_code == 200, "the score must still be returned"
    b = r.json()
    assert b["sif_probability"] > 0
    assert b["recorded"] is False, "and it must say the history was not written"
    assert b["obs_id"] is None
    assert c.get("/health").json()["store_enabled"] is False


@pytest.mark.model
def test_score_without_a_site_records_nothing(client, tmp_path):
    """Backward compatibility: the old contract is untouched."""
    b = client.post("/score", json={"narrative": SEVERE}).json()
    assert b["recorded"] is False
    assert b["obs_id"] is None
    assert b["site_id"] is None


@pytest.mark.model
def test_score_with_a_site_is_recorded_and_readable_back(make_client, tmp_path):
    db = tmp_path / "observations.db"
    c = make_client(SIF_RATE_LIMIT=0, SIF_STORE_DB=str(db))
    b = c.post("/score", json={"narrative": SEVERE, "site_id": "rig-7"}).json()
    assert b["recorded"] is True
    assert b["obs_id"]
    assert b["site_id"] == "rig-7"

    with Store(db) as s:
        rows = s.observations(site_id="rig-7")
    assert len(rows) == 1
    assert rows[0].obs_id == b["obs_id"]
    assert rows[0].sif_probability == pytest.approx(b["sif_probability"], abs=1e-3)


@pytest.mark.model
def test_reposting_the_same_report_does_not_duplicate_it(make_client, tmp_path):
    db = tmp_path / "observations.db"
    c = make_client(SIF_RATE_LIMIT=0, SIF_STORE_DB=str(db))
    when = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    payload = {"narrative": SEVERE, "site_id": "rig-7", "occurred_at": when}
    first = c.post("/score", json=payload).json()
    again = c.post("/score", json=payload).json()
    assert first["obs_id"] == again["obs_id"]
    with Store(db) as s:
        assert s.count() == 1


@pytest.mark.model
def test_occurred_at_drives_the_recorded_timestamp(make_client, tmp_path):
    db = tmp_path / "observations.db"
    c = make_client(SIF_RATE_LIMIT=0, SIF_STORE_DB=str(db))
    when = datetime.now(timezone.utc) - timedelta(days=30)
    c.post("/score", json={"narrative": SEVERE, "site_id": "rig-7",
                           "occurred_at": when.isoformat()})
    with Store(db) as s:
        recorded = s.observations()[0].timestamp
    assert abs((recorded - when).total_seconds()) < 2


@pytest.mark.model
def test_end_to_end_scored_reports_become_a_site_assessment(make_client, tmp_path):
    c = make_client(SIF_RATE_LIMIT=0, SIF_STORE_DB=str(tmp_path / "obs.db"))
    for text in (HEIGHT_A, HEIGHT_B, HOTWORK, PERMIT):
        assert c.post("/score", json={"narrative": text,
                                      "site_id": "rig-7"}).json()["recorded"] is True
    d = c.get("/sites/rig-7").json()
    assert d["n_observations"] == 4
    assert d["n_clusters"] >= 2
    assert d["explanation"]


@pytest.mark.model
def test_score_explains_which_rule_it_touched(client):
    b = client.post("/score", json={
        "narrative": "The crew began breaking the flange before the permit to work "
                     "had been issued."}).json()
    names = [r["rule_name"] for r in b["rules"]]
    assert "Work Authorisation" in names
    top = b["rules"][0]
    assert top["evidence"], "a match must show what triggered it"
    assert top["suggested_checks"], "and what to check"
    assert "IOGP" in top["source"]


@pytest.mark.model
def test_no_rule_match_is_not_a_safety_judgement(client):
    """An empty rules list must not imply low risk -- the score is independent."""
    b = client.post("/score", json={"narrative": TRIVIAL}).json()
    assert isinstance(b["rules"], list)
    assert 0.0 <= b["sif_probability"] <= 1.0


def test_batch_rejects_a_sites_list_of_the_wrong_length(client):
    r = client.post("/score/batch", json={"narratives": [SEVERE, TRIVIAL],
                                          "sites": ["rig-7"]})
    assert r.status_code == 422, "a short sites list would silently drop reports"


def test_batch_rejects_site_id_and_sites_together(client):
    r = client.post("/score/batch", json={"narratives": [SEVERE], "site_id": "a",
                                          "sites": ["b"]})
    assert r.status_code == 422


@pytest.mark.model
def test_batch_keeps_each_site_with_its_own_narrative_through_reranking(
        make_client, tmp_path):
    """The results are reordered by score. If sites were zipped against the"""
    db = tmp_path / "observations.db"
    c = make_client(SIF_RATE_LIMIT=0, SIF_STORE_DB=str(db))
    subs = [TRIVIAL, SEVERE, TRIVIAL]
    b = c.post("/score/batch", json={"narratives": subs,
                                     "sites": ["office", "rig-7", "office"]}).json()

    by_text = {r["narrative"]: r["site_id"] for r in b["results"]}
    assert by_text[SEVERE] == "rig-7"
    assert by_text[TRIVIAL] == "office"
    assert b["results"][0]["narrative"] == SEVERE, "still ranked by risk"

    with Store(db) as s:
        assert [o.narrative for o in s.observations(site_id="rig-7")] == [SEVERE]
        assert len(s.observations(site_id="office")) == 1


@pytest.mark.model
def test_batch_site_id_applies_to_everything(make_client, tmp_path):
    db = tmp_path / "observations.db"
    c = make_client(SIF_RATE_LIMIT=0, SIF_STORE_DB=str(db))
    b = c.post("/score/batch", json={"narratives": [HEIGHT_A, HOTWORK],
                                     "site_id": "rig-7"}).json()
    assert all(r["recorded"] for r in b["results"])
    with Store(db) as s:
        assert s.sites() == ["rig-7"]
        assert s.count() == 2


@pytest.mark.model
def test_batch_without_sites_stores_nothing(make_client, tmp_path):
    db = tmp_path / "observations.db"
    c = make_client(SIF_RATE_LIMIT=0, SIF_STORE_DB=str(db))
    b = c.post("/score/batch", json={"narratives": [SEVERE, TRIVIAL]}).json()
    assert not any(r["recorded"] for r in b["results"])
    with Store(db) as s:
        assert s.count() == 0


def test_dashboard_is_served(client):
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "<title>" in r.text


def test_dashboard_needs_no_key_but_its_data_does(make_client, seeded):
    """The page is an empty shell; every request it makes is authenticated."""
    c = make_client(SIF_API_KEYS="k1", SIF_RATE_LIMIT=0, SIF_STORE_DB=str(seeded))
    assert c.get("/dashboard").status_code == 200
    assert c.get("/sites").status_code == 401


def test_dashboard_is_the_same_shell_whatever_the_store_holds(make_client, seeded,
                                                              tmp_path):
    """It renders nothing server-side, so the page cannot leak incident data."""
    loaded = make_client(SIF_RATE_LIMIT=0, SIF_STORE_DB=str(seeded)).get("/dashboard").text
    empty = make_client(SIF_RATE_LIMIT=0,
                        SIF_STORE_DB=str(tmp_path / "empty.db")).get("/dashboard").text
    assert loaded == empty
    assert "duliajan" not in loaded.lower()


def test_dashboard_states_the_limitations_on_screen(client):
    """api/README.md asks for these to be surfaced in the UI, not a footnote."""
    body = client.get("/dashboard").text
    for phrase in ("unvalidated aggregation policy", "ranker",
                   "does not replace human judgement"):
        assert phrase in body, f"the dashboard stopped saying {phrase!r}"


def test_dashboard_loads_no_third_party_resources(client):
    """No CDN, so it works offline and in the container. Also means nothing"""
    body = client.get("/dashboard").text
    for marker in ("http://", "https://"):
        for line in body.splitlines():
            if marker in line and "iogp.org" not in line:
                assert "src=" not in line and "href=" not in line, \
                    f"external resource: {line.strip()[:90]}"


def test_dashboard_reports_its_own_absence(client, monkeypatch, tmp_path):
    from api import main

    monkeypatch.setattr(main, "DASHBOARD", tmp_path / "gone.html")
    r = client.get("/dashboard")
    assert r.status_code == 503
    assert "not installed" in r.json()["detail"]


def test_site_endpoints_require_a_key_when_auth_is_on(make_client, seeded):
    """Site history is a richer target than a single score: it is the operator's"""
    c = make_client(SIF_API_KEYS="k1", SIF_RATE_LIMIT=0, SIF_STORE_DB=str(seeded))
    assert c.get("/sites").status_code == 401
    assert c.get("/sites/duliajan-rig-7").status_code == 401
    assert c.get("/sites", headers={"X-API-Key": "k1"}).status_code == 200
