"""Site-level risk aggregation and its store."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from ml.clustering import (
    Observation,
    RiskParams,
    assess_all,
    assess_site,
    cluster_observations,
    combine,
    level_for,
    similarity,
)
from ml.store import Store

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)

HEIGHT_A = ("A scaffold plank on the north platform moved underfoot as a fitter "
            "stepped onto it at about 8 metres.")
HEIGHT_B = ("Fitter working at height on the same platform had his harness lanyard "
            "clipped to the scaffold tube rather than the anchor point.")
HOTWORK = ("Gas detector at the welding bay was three weeks out of calibration; hot "
           "work was stopped.")
PERMIT = ("Crew began breaking the flange on the test line before the permit to work "
          "had come back signed.")


def _distinct_word(n: int) -> str:
    """A unique, letters-only token."""
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(97 + r) + s
    return "qq" + s


def obs(text, p, days_ago=0, site="rig-7", rules=(), oid=None):
    return Observation(
        obs_id=oid or f"o{abs(hash((text, days_ago))) % 10**8}",
        site_id=site,
        timestamp=NOW - timedelta(days=days_ago),
        narrative=text,
        sif_probability=p,
        rules=tuple(rules),
    )


def test_decay_halves_at_the_half_life():
    o = obs(HEIGHT_A, 0.40, days_ago=30)
    assert o.decay(NOW, 30.0) == pytest.approx(0.5)
    assert o.weighted(NOW, 30.0) == pytest.approx(0.20)


def test_fresh_report_is_undecayed():
    assert obs(HEIGHT_A, 0.40, days_ago=0).weighted(NOW, 30.0) == pytest.approx(0.40)


def test_reports_outside_the_window_are_dropped():
    r = assess_site([obs(HEIGHT_A, 0.9, days_ago=200)], asof=NOW)
    assert r.n_observations == 0
    assert r.site_risk == 0.0
    assert r.level == "NORMAL"


def test_same_rule_links_two_reports():
    a = obs(HEIGHT_A, 0.4, rules=["working_at_height"])
    b = obs(HEIGHT_B, 0.4, 2, rules=["working_at_height"])
    assert similarity(a, b, RiskParams()) >= RiskParams().link_threshold
    assert len(cluster_observations([a, b])) == 1


def test_different_hazards_stay_apart():
    a = obs(HEIGHT_A, 0.4, rules=["working_at_height"])
    b = obs(HOTWORK, 0.4, 1, rules=["hot_work"])
    c = obs(PERMIT, 0.4, 2, rules=["work_authorisation"])
    assert len(cluster_observations([a, b, c])) == 3


def test_clustering_is_order_independent():
    rows = [obs(HEIGHT_A, 0.4, 1, rules=["working_at_height"]),
            obs(HEIGHT_B, 0.4, 2, rules=["working_at_height"]),
            obs(HOTWORK, 0.4, 3, rules=["hot_work"])]
    a = sorted(len(g) for g in cluster_observations(rows))
    b = sorted(len(g) for g in cluster_observations(list(reversed(rows))))
    assert a == b == [1, 2]


def test_clusters_without_rules_still_link_on_wording():
    """SIF_STORE_TEXT is on, rules missing: lexical overlap alone must cluster."""
    a = obs(HEIGHT_A, 0.4)
    b = obs(HEIGHT_A + " He steadied himself on the handrail.", 0.4, 1)
    assert len(cluster_observations([a, b])) == 1


def test_clusters_without_text_still_link_on_rules():
    """SIF_STORE_TEXT=0: no narrative, so only rule overlap can carry it."""
    a = obs("", 0.4, rules=["hot_work"])
    b = obs("", 0.4, 1, rules=["hot_work"])
    assert len(cluster_observations([a, b])) == 1


def test_observation_with_neither_text_nor_rules_is_a_singleton():
    rows = [obs("", 0.4), obs("", 0.4, 1)]
    assert len(cluster_observations(rows)) == 2


def test_recurrence_raises_a_repeated_hazard_above_its_best_report():
    single = assess_site([obs(HEIGHT_A, 0.40, rules=["working_at_height"])], asof=NOW)
    repeated = assess_site(
        [obs(HEIGHT_A, 0.40, 0, rules=["working_at_height"]),
         obs(HEIGHT_B, 0.38, 1, rules=["working_at_height"])],
        asof=NOW,
    )
    assert len(repeated.clusters) == 1
    assert repeated.clusters[0].strength > single.clusters[0].strength


def test_recurrence_is_sublinear():
    """Doubling reports adds a fixed amount, so the 8th matters less than the 2nd."""
    def strength(n):
        rows = [obs(HEIGHT_A + f" occurrence {i}", 0.40, i * 0.01,
                    rules=["working_at_height"]) for i in range(n)]
        r = assess_site(rows, asof=NOW)
        assert len(r.clusters) == 1, "test setup should produce one cluster"
        return r.clusters[0].strength

    s1, s2, s4, s8 = strength(1), strength(2), strength(4), strength(8)
    assert s1 < s2 < s4 < s8
    assert (s8 - s4) == pytest.approx(s4 - s2, abs=0.01)
    assert (s4 - s2) <= (s2 - s1) + 1e-9


def test_recurrence_never_exceeds_one():
    rows = [obs(HEIGHT_A + f" {i}", 0.99, 0, rules=["working_at_height"])
            for i in range(50)]
    r = assess_site(rows, asof=NOW)
    assert r.clusters[0].strength <= 1.0


def test_stale_repeats_count_for_less_than_fresh_ones():
    fresh = assess_site([obs(HEIGHT_A, 0.4, 0, rules=["working_at_height"]),
                         obs(HEIGHT_B, 0.4, 1, rules=["working_at_height"])], asof=NOW)
    stale = assess_site([obs(HEIGHT_A, 0.4, 0, rules=["working_at_height"]),
                         obs(HEIGHT_B, 0.4, 80, rules=["working_at_height"])], asof=NOW)
    assert fresh.clusters[0].strength > stale.clusters[0].strength


def test_convergence_puts_the_site_above_its_worst_report():
    rows = [obs(HEIGHT_A, 0.35, 1, rules=["working_at_height"]),
            obs(HOTWORK, 0.35, 2, rules=["hot_work"]),
            obs(PERMIT, 0.35, 3, rules=["work_authorisation"])]
    r = assess_site(rows, asof=NOW)
    assert len(r.clusters) == 3
    assert r.site_risk > r.max_report_probability
    assert r.escalation > 0.25


def test_convergence_flags_compounding_when_nothing_individual_would():
    """The headline case: five dull reports, none reviewable, site is not."""
    p = RiskParams()
    rows = [obs(HEIGHT_A, 0.45, 1, rules=["working_at_height"]),
            obs(HEIGHT_B, 0.42, 2, rules=["working_at_height"]),
            obs(HOTWORK, 0.38, 4, rules=["hot_work"]),
            obs(PERMIT, 0.36, 6, rules=["work_authorisation"])]
    r = assess_site(rows, asof=NOW)
    assert all(o.sif_probability < p.review_threshold for o in rows)
    assert r.site_risk >= p.review_threshold
    assert r.compounding is True
    assert "COMPOUNDING" in r.explain()


def test_not_compounding_when_a_single_report_already_crosses():
    """One alarming report is per-report triage's job, not this module's alert."""
    rows = [obs(HEIGHT_A, 0.80, 1, rules=["working_at_height"]),
            obs(HOTWORK, 0.30, 2, rules=["hot_work"])]
    r = assess_site(rows, asof=NOW)
    assert r.site_risk >= RiskParams().review_threshold
    assert r.compounding is False


def test_one_hazard_repeated_is_not_treated_as_convergence():
    """Four reports of the same plank must stay well below four distinct hazards."""
    same = assess_site([obs(HEIGHT_A + f" {i}", 0.35, i, rules=["working_at_height"])
                        for i in range(4)], asof=NOW)
    distinct = assess_site(
        [obs(HEIGHT_A, 0.35, 0, rules=["working_at_height"]),
         obs(HOTWORK, 0.35, 1, rules=["hot_work"]),
         obs(PERMIT, 0.35, 2, rules=["work_authorisation"]),
         obs("Reversing vehicle came within a metre of a banksman.", 0.35, 3,
             rules=["driving"])],
        asof=NOW,
    )
    assert len(same.clusters) == 1
    assert len(distinct.clusters) == 4
    assert distinct.site_risk > same.site_risk + 0.2


def test_quiet_site_stays_normal():
    rows = [obs("Printer in the HSE office ran out of toner.", 0.19, 6),
            obs("Cable reel left across the walkway near the store, moved aside.", 0.22, 40)]
    r = assess_site(rows, asof=NOW)
    assert r.level == "NORMAL"
    assert r.compounding is False


def test_weak_clusters_are_excluded_from_the_combination():
    p = RiskParams(min_cluster_strength=0.10)
    rows = [obs(HEIGHT_A, 0.40, 1, rules=["working_at_height"]),
            obs(HOTWORK, 0.02, 2, rules=["hot_work"])]
    r = assess_site(rows, asof=NOW, params=p)
    assert len(r.clusters) == 2
    assert len(r.contributing) == 1
    assert r.site_risk == pytest.approx(r.clusters[0].strength, abs=1e-9)


def test_max_clusters_caps_saturation():
    """Thirty genuinely distinct groups must not reach 1.00 on volume alone."""
    p = RiskParams(max_clusters=8)
    rows = [obs(" ".join(_distinct_word(3 * i + k) for k in range(3)), 0.20,
                i % 30, rules=[f"rule_{i}"]) for i in range(30)]
    r = assess_site(rows, asof=NOW, params=p)
    assert len(r.clusters) == 30
    assert r.site_risk < 1.0
    capped = combine(sorted(r.clusters, key=lambda c: -c.strength)[:8], p)
    assert r.site_risk == pytest.approx(capped)


def test_losing_rule_tags_splits_one_hazard_and_inflates_the_site():
    """Pinned because this degradation runs the unsafe way."""
    a_text = "A scaffold plank on the north platform moved underfoot at about 8 metres."
    b_text = "Lanyard was clipped to a handrail instead of the designated anchor point."

    def site(rules):
        return assess_site([obs(a_text, 0.40, 0, rules=rules),
                            obs(b_text, 0.38, 1, rules=rules)], asof=NOW)

    tagged = site(["working_at_height"])
    untagged = site([])
    assert len(tagged.clusters) == 1
    assert len(untagged.clusters) == 2
    assert untagged.site_risk > tagged.site_risk


def test_digits_do_not_distinguish_two_narratives():
    """Known limitation, pinned. Tokenisation is `[a-z]+`, so equipment tags and"""
    a = obs("Seal leak found on pump P-101 in the manifold area.", 0.3)
    b = obs("Seal leak found on pump P-205 in the manifold area.", 0.3, 1)
    assert similarity(a, b, RiskParams()) == pytest.approx(0.4)
    assert len(cluster_observations([a, b])) == 1


def test_single_link_chains_reports_worded_alike():
    """Known limitation, pinned rather than papered over."""
    rows = [obs(f"unrelated minor condition number {i} in area {i}", 0.20, i,
                rules=[f"rule_{i}"]) for i in range(6)]
    assert len(cluster_observations(rows)) == 1


def test_combine_matches_noisy_or_by_hand():
    p = RiskParams()
    rows = [obs(HEIGHT_A, 0.35, 0, rules=["working_at_height"]),
            obs(HOTWORK, 0.35, 0, rules=["hot_work"]),
            obs(PERMIT, 0.35, 0, rules=["work_authorisation"])]
    r = assess_site(rows, asof=NOW, params=p)
    expected = 1.0
    for c in r.clusters:
        expected *= (1 - c.strength)
    assert r.site_risk == pytest.approx(1 - expected)


def test_levels_are_ordered_and_reachable():
    p = RiskParams()
    assert level_for(0.00, p) == "NORMAL"
    assert level_for(0.40, p) == "WATCH"
    assert level_for(0.60, p) == "HIGH"
    assert level_for(0.90, p) == "CRITICAL"


def test_trend_rises_when_recent_half_is_worse():
    rows = [obs(HOTWORK, 0.20, 80, rules=["hot_work"]),
            obs(HEIGHT_A, 0.45, 5, rules=["working_at_height"]),
            obs(PERMIT, 0.40, 3, rules=["work_authorisation"])]
    r = assess_site(rows, asof=NOW)
    assert r.trend == "rising"
    assert r.trend_delta > 0


def test_trend_falls_when_the_site_is_settling():
    rows = [obs(HEIGHT_A, 0.45, 80, rules=["working_at_height"]),
            obs(HOTWORK, 0.40, 75, rules=["hot_work"]),
            obs(PERMIT, 0.15, 3, rules=["work_authorisation"])]
    r = assess_site(rows, asof=NOW)
    assert r.trend == "falling"
    assert r.trend_delta < 0


def test_trend_needs_both_halves():
    r = assess_site([obs(HEIGHT_A, 0.4, 2, rules=["working_at_height"])], asof=NOW)
    assert r.trend == "insufficient history"
    assert "Trend" not in r.explain()


def test_explanation_marks_every_group_it_did_not_count():
    """The listed groups must account for the headline number, or the"""
    p = RiskParams(max_clusters=3)
    rows = [obs(" ".join(_distinct_word(3 * i + k) for k in range(3)), 0.30, i,
                rules=[f"rule_{i}"]) for i in range(5)]
    rows.append(obs(_distinct_word(99), 0.01, 0, rules=["rule_floor"]))
    text = assess_site(rows, asof=NOW, params=p).explain()
    assert text.count("not counted") == 3
    assert "past the 3-group cap" in text
    assert "below floor" in text


def test_explanation_names_the_evidence():
    rows = [obs(HEIGHT_A, 0.45, 1, rules=["working_at_height"]),
            obs(HOTWORK, 0.38, 3, rules=["hot_work"])]
    text = assess_site(rows, asof=NOW).explain()
    assert "Working at Height" in text
    assert "Hot Work" in text
    assert "scaffold plank" in text


def test_cluster_label_names_only_rules_the_members_agree_on():
    """One loose match in one narrative must not name the whole cluster."""
    rows = [obs(HOTWORK, 0.30, 0, rules=["hot_work"]),
            obs(HOTWORK + " Vessel entry was not involved.", 0.30, 1,
                rules=["hot_work", "confined_space"])]
    r = assess_site(rows, asof=NOW)
    assert len(r.clusters) == 1
    assert r.clusters[0].label == "Hot Work"


def test_result_is_serialisable_and_carries_its_params():
    r = assess_site([obs(HEIGHT_A, 0.45, 1, rules=["working_at_height"])], asof=NOW)
    d = r.to_dict()
    assert d["params"]["half_life_days"] == 30.0
    assert d["level"] in ("CRITICAL", "HIGH", "WATCH", "NORMAL")
    assert "not a measured probability" in d["caveat"]
    import json

    json.loads(json.dumps(d))


def test_assessment_is_reproducible_for_a_fixed_asof():
    rows = [obs(HEIGHT_A, 0.45, 1, rules=["working_at_height"]),
            obs(HOTWORK, 0.38, 3, rules=["hot_work"])]
    a = assess_site(rows, asof=NOW).to_dict()
    b = assess_site(rows, asof=NOW).to_dict()
    assert a == b


def test_assess_all_groups_by_site_and_ranks():
    rows = [obs(HEIGHT_A, 0.45, 1, site="rig-7", rules=["working_at_height"]),
            obs(HOTWORK, 0.40, 2, site="rig-7", rules=["hot_work"]),
            obs("Printer ran out of toner.", 0.15, 1, site="office")]
    out = assess_all(rows, asof=NOW)
    assert [r.site_id for r in out] == ["rig-7", "office"]
    assert out[0].site_risk > out[1].site_risk


def test_empty_input_is_not_an_error():
    r = assess_site([], asof=NOW)
    assert r.site_risk == 0.0
    assert r.n_observations == 0
    assert "No reports in the window." in r.explain()


@pytest.fixture
def store(tmp_path):
    with Store(tmp_path / "obs.db") as s:
        yield s


def test_store_round_trips_an_observation(store):
    store.record("rig-7", HEIGHT_A, 0.45, timestamp=NOW - timedelta(days=2),
                 rules=["working_at_height"], band="ELEVATED")
    got = store.observations(site_id="rig-7")
    assert len(got) == 1
    assert got[0].sif_probability == pytest.approx(0.45)
    assert got[0].rules == ("working_at_height",)
    assert got[0].narrative == HEIGHT_A


def test_store_ingest_is_idempotent(store):
    for _ in range(3):
        store.record("rig-7", HEIGHT_A, 0.45, timestamp=NOW)
    assert store.count() == 1


def test_same_text_at_a_later_date_is_recurrence_not_a_duplicate(store):
    store.record("rig-7", HEIGHT_A, 0.45, timestamp=NOW - timedelta(days=7))
    store.record("rig-7", HEIGHT_A, 0.45, timestamp=NOW)
    assert store.count() == 2


def test_same_text_at_two_sites_stays_separate(store):
    store.record("rig-7", HEIGHT_A, 0.45, timestamp=NOW)
    store.record("moran-cpf", HEIGHT_A, 0.45, timestamp=NOW)
    assert store.sites() == ["moran-cpf", "rig-7"]
    assert len(store.observations(site_id="rig-7")) == 1


def test_store_filters_by_window(store):
    store.record("rig-7", HEIGHT_A, 0.45, timestamp=NOW - timedelta(days=200))
    store.record("rig-7", HOTWORK, 0.38, timestamp=NOW - timedelta(days=3))
    assert len(store.observations(since_days=90, asof=NOW)) == 1


def test_store_returns_oldest_first(store):
    store.record("rig-7", HOTWORK, 0.38, timestamp=NOW - timedelta(days=1))
    store.record("rig-7", HEIGHT_A, 0.45, timestamp=NOW - timedelta(days=9))
    ts = [o.timestamp for o in store.observations(site_id="rig-7")]
    assert ts == sorted(ts)


def test_naive_timestamps_are_read_as_utc(store):
    store.record("rig-7", HEIGHT_A, 0.45, timestamp=datetime(2026, 6, 1, 12, 0))
    assert store.observations()[0].timestamp == NOW


def test_store_text_can_be_switched_off(monkeypatch, tmp_path):
    """The privacy setting must degrade clustering, not break it."""
    monkeypatch.setenv("SIF_STORE_TEXT", "0")
    with Store(tmp_path / "obs.db") as s:
        s.record("rig-7", HEIGHT_A, 0.45, timestamp=NOW, rules=["working_at_height"])
        s.record("rig-7", HEIGHT_B, 0.42, timestamp=NOW - timedelta(days=1),
                 rules=["working_at_height"])
        got = s.observations()
    assert all(o.narrative == "" for o in got)
    r = assess_site(got, asof=NOW)
    assert len(r.clusters) == 1


def test_store_feeds_the_assessment_end_to_end(store):
    rows = [(HEIGHT_A, 0.45, 1, ["working_at_height"]),
            (HEIGHT_B, 0.42, 2, ["working_at_height"]),
            (HOTWORK, 0.38, 4, ["hot_work"]),
            (PERMIT, 0.36, 6, ["work_authorisation"])]
    for text, p, days, rules in rows:
        store.record("rig-7", text, p, timestamp=NOW - timedelta(days=days), rules=rules)
    r = assess_site(store.observations(site_id="rig-7", asof=NOW), asof=NOW)
    assert r.n_observations == 4
    assert r.compounding is True


def test_store_defaults_to_env_db(monkeypatch, tmp_path):
    target = tmp_path / "from_env.db"
    monkeypatch.setenv("SIF_STORE_DB", str(target))
    with Store() as s:
        s.record("rig-7", HEIGHT_A, 0.45, timestamp=NOW)
    assert target.exists()
    assert os.path.getsize(target) > 0
