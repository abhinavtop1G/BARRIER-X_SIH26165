#!/usr/bin/env python3
"""ml/clustering.py  --  the site is more dangerous than any of its reports"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


SITE_LEVELS = ("CRITICAL", "HIGH", "WATCH", "NORMAL")

LEVEL_GUIDANCE = {
    "CRITICAL": "Stop and review the site, not just the reports.",
    "HIGH": "Several hazards are live together. Schedule a site walkdown.",
    "WATCH": "Accumulating. Worth a look before it grows.",
    "NORMAL": "Nothing at site level beyond the individual reports.",
}


@dataclass(frozen=True)
class RiskParams:
    """Every constant in one place, recorded in every result."""

    window_days: float = 90.0
    half_life_days: float = 30.0

    link_threshold: float = 0.30
    rule_weight: float = 0.60
    lexical_weight: float = 0.40

    recurrence_gain: float = 0.15

    min_cluster_strength: float = 0.10
    max_clusters: int = 8

    review_threshold: float = 0.50
    level_watch: float = 0.35
    level_high: float = 0.55
    level_critical: float = 0.75

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Observation:
    """One scored report. Produced by `ml/store.py`, or built directly in tests."""

    obs_id: str
    site_id: str
    timestamp: datetime
    narrative: str
    sif_probability: float
    rules: tuple[str, ...] = ()
    band: str = ""

    def age_days(self, asof: datetime) -> float:
        return max(0.0, (asof - self.timestamp).total_seconds() / 86400.0)

    def decay(self, asof: datetime, half_life_days: float) -> float:
        return 0.5 ** (self.age_days(asof) / half_life_days)

    def weighted(self, asof: datetime, half_life_days: float) -> float:
        return self.sif_probability * self.decay(asof, half_life_days)


@dataclass
class Cluster:
    """One hazard, and every report of it inside the window."""

    cluster_id: int
    label: str
    rule_ids: list[str]
    members: list[Observation]
    peak: float
    weight: float
    strength: float
    peak_obs_id: str = ""

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def latest(self) -> datetime:
        return max(o.timestamp for o in self.members)

    @property
    def recurrence_bonus(self) -> float:
        return self.strength - self.peak

    def to_dict(self) -> dict:
        return {
            "cluster_id": self.cluster_id,
            "label": self.label,
            "rule_ids": self.rule_ids,
            "size": self.size,
            "peak": round(self.peak, 4),
            "effective_count": round(self.weight, 3),
            "recurrence_bonus": round(self.recurrence_bonus, 4),
            "strength": round(self.strength, 4),
            "latest": self.latest.isoformat(),
            "peak_obs_id": self.peak_obs_id,
            "members": [
                {
                    "obs_id": o.obs_id,
                    "timestamp": o.timestamp.isoformat(),
                    "sif_probability": round(o.sif_probability, 4),
                    "rules": list(o.rules),
                    "narrative": o.narrative[:300],
                }
                for o in sorted(self.members, key=lambda m: -m.sif_probability)
            ],
        }


@dataclass
class SiteRisk:
    """What the site looks like as a whole, and why."""

    site_id: str
    asof: datetime
    site_risk: float
    level: str
    max_report_probability: float
    escalation: float
    compounding: bool
    clusters: list[Cluster]
    n_observations: int
    trend: str
    trend_delta: float
    params: RiskParams = field(default_factory=RiskParams)

    @property
    def contributing(self) -> list[Cluster]:
        return [c for c in self.clusters if c.strength >= self.params.min_cluster_strength][
            : self.params.max_clusters
        ]

    def to_dict(self) -> dict:
        return {
            "site_id": self.site_id,
            "asof": self.asof.isoformat(),
            "site_risk": round(self.site_risk, 4),
            "level": self.level,
            "guidance": LEVEL_GUIDANCE[self.level],
            "max_report_probability": round(self.max_report_probability, 4),
            "escalation": round(self.escalation, 4),
            "compounding": self.compounding,
            "n_observations": self.n_observations,
            "n_clusters": len(self.clusters),
            "trend": self.trend,
            "trend_delta": round(self.trend_delta, 4),
            "clusters": [c.to_dict() for c in self.clusters],
            "explanation": self.explain(),
            "params": self.params.to_dict(),
            "caveat": (
                "Site risk is an unvalidated aggregation policy, not a measured "
                "probability. Only the per-report scores it combines have a "
                "PR-AUC behind them (docs/RESULTS.md)."
            ),
        }

    def explain(self) -> str:
        """A summary a safety officer can act on, or disagree with, without"""
        p = self.params
        out: list[str] = []
        window = int(p.window_days)
        out.append(
            f"{self.site_id}: site risk {self.site_risk:.2f} ({self.level}) from "
            f"{self.n_observations} report(s) in the last {window} days, "
            f"in {len(self.clusters)} hazard group(s)."
        )
        out.append(LEVEL_GUIDANCE[self.level])

        if self.compounding:
            out.append(
                f"COMPOUNDING: no single report reached the {p.review_threshold:.2f} "
                f"review threshold -- the highest was {self.max_report_probability:.2f} -- "
                f"but {len(self.contributing)} hazard groups are live at once, which "
                f"together clear it. Per-report triage would not have surfaced this site."
            )
        elif self.escalation >= 0.10:
            out.append(
                f"The site scores {self.escalation:.2f} above its worst single report "
                f"({self.max_report_probability:.2f}); the accumulation is doing that, "
                f"not any one narrative."
            )

        if self.trend != "insufficient history":
            out.append(
                f"Trend over the window: {self.trend} ({self.trend_delta:+.2f} "
                f"recent half vs. prior half)."
            )

        if not self.clusters:
            out.append("No reports in the window.")
            return "\n".join(out)

        out.append("")
        out.append("Hazard groups, strongest first:")
        contributing = {c.cluster_id for c in self.contributing}
        for c in self.clusters:
            age = (self.asof - c.latest).days
            if c.cluster_id in contributing:
                counted = ""
            elif c.strength < p.min_cluster_strength:
                counted = "   [below floor, not counted]"
            else:
                counted = f"   [past the {p.max_clusters}-group cap, not counted]"
            out.append(
                f"  {c.strength:.2f}  {c.label}  --  {c.size} report(s), "
                f"latest {age}d ago{counted}"
            )
            if c.size > 1:
                out.append(
                    f"          strongest {c.peak:.2f} after decay; recurrence "
                    f"(x{c.weight:.1f} effective) added {c.recurrence_bonus:+.2f}"
                )
            top = max(c.members, key=lambda m: m.sif_probability)
            snippet = " ".join(top.narrative.split())[:150]
            if snippet:
                out.append(f'          "{snippet}{"..." if len(top.narrative) > 150 else ""}"')
        return "\n".join(out)


def _tokens(text: str) -> set[str]:
    """Stemmed, stopworded tokens."""
    try:
        from ml.rules import tokens as rule_tokens

        return rule_tokens(text)
    except Exception:
        return {w for w in text.lower().split() if len(w) > 3}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def similarity(a: Observation, b: Observation, params: RiskParams) -> float:
    """How much two reports look like the same hazard, in [0, 1]."""
    rule_sim = jaccard(set(a.rules), set(b.rules))
    lex_sim = jaccard(_tokens(a.narrative), _tokens(b.narrative))
    return params.rule_weight * rule_sim + params.lexical_weight * lex_sim


def cluster_observations(obs: list[Observation],
                         params: RiskParams | None = None) -> list[list[Observation]]:
    """Single-link agglomerative clustering at `link_threshold`."""
    p = params or RiskParams()
    n = len(obs)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)

    for i in range(n):
        for j in range(i + 1, n):
            if similarity(obs[i], obs[j], p) >= p.link_threshold:
                union(i, j)

    groups: dict[int, list[Observation]] = {}
    for i, o in enumerate(obs):
        groups.setdefault(find(i), []).append(o)
    return list(groups.values())


def _label_for(rule_ids: list[str], counts: dict[str, int],
               members: list[Observation]) -> str:
    """Name the cluster after the rules its members agree on."""
    if rule_ids:
        best = counts[rule_ids[0]]
        dominant = [r for r in rule_ids if counts[r] == best][:2]
        try:
            from ml.rules import get_matcher

            names = {r["id"]: r["name"] for r in get_matcher().rules}
            return " + ".join(names.get(r, r) for r in dominant)
        except Exception:
            return " + ".join(dominant)
    text = " ".join(m.narrative for m in members)
    keys = sorted(_tokens(text))[:3]
    return ("unclassified: " + ", ".join(keys)) if keys else "unclassified"


def build_cluster(cluster_id: int, members: list[Observation], asof: datetime,
                  params: RiskParams) -> Cluster:
    """Collapse one hazard group into a single strength."""
    weighted = [(o, o.weighted(asof, params.half_life_days)) for o in members]
    peak_obs, peak = max(weighted, key=lambda t: t[1])
    weight = max(1.0, sum(o.decay(asof, params.half_life_days) for o in members))
    strength = min(1.0, peak * (1.0 + params.recurrence_gain * math.log2(weight)))

    counts: dict[str, int] = {}
    for o in members:
        for r in o.rules:
            counts[r] = counts.get(r, 0) + 1
    rule_ids = sorted(counts, key=lambda r: (-counts[r], r))

    return Cluster(
        cluster_id=cluster_id,
        label=_label_for(rule_ids, counts, members),
        rule_ids=rule_ids,
        members=members,
        peak=peak,
        weight=weight,
        strength=strength,
        peak_obs_id=peak_obs.obs_id,
    )


def combine(clusters: list[Cluster], params: RiskParams) -> float:
    """Noisy-OR across hazard groups: 1 - prod(1 - strength)."""
    live = sorted((c for c in clusters if c.strength >= params.min_cluster_strength),
                  key=lambda c: -c.strength)[: params.max_clusters]
    survive = 1.0
    for c in live:
        survive *= (1.0 - c.strength)
    return 1.0 - survive


def level_for(risk: float, params: RiskParams) -> str:
    if risk >= params.level_critical:
        return "CRITICAL"
    if risk >= params.level_high:
        return "HIGH"
    if risk >= params.level_watch:
        return "WATCH"
    return "NORMAL"


def _risk_of(obs: list[Observation], asof: datetime, params: RiskParams) -> float:
    if not obs:
        return 0.0
    groups = cluster_observations(obs, params)
    clusters = [build_cluster(i, g, asof, params) for i, g in enumerate(groups)]
    return combine(clusters, params)


def _trend(obs: list[Observation], asof: datetime,
           params: RiskParams) -> tuple[str, float]:
    """Recent half of the window against the prior half."""
    half = params.window_days / 2.0
    mid = asof - timedelta(days=half)
    recent = [o for o in obs if o.timestamp >= mid]
    prior = [o for o in obs if o.timestamp < mid]
    if not recent or not prior:
        return "insufficient history", 0.0

    delta = _risk_of(recent, asof, params) - _risk_of(prior, mid, params)
    if delta >= 0.10:
        return "rising", delta
    if delta <= -0.10:
        return "falling", delta
    return "steady", delta


def assess_site(observations: list[Observation], asof: datetime | None = None,
                params: RiskParams | None = None,
                site_id: str | None = None) -> SiteRisk:
    """Score one site from its recent reports."""
    p = params or RiskParams()
    now = asof or datetime.now(timezone.utc)
    site = site_id or (observations[0].site_id if observations else "unknown")

    cutoff = now - timedelta(days=p.window_days)
    live = [o for o in observations if o.timestamp >= cutoff]

    if not live:
        return SiteRisk(
            site_id=site, asof=now, site_risk=0.0, level="NORMAL",
            max_report_probability=0.0, escalation=0.0, compounding=False,
            clusters=[], n_observations=0, trend="insufficient history",
            trend_delta=0.0, params=p,
        )

    groups = cluster_observations(live, p)
    clusters = sorted(
        (build_cluster(i, g, now, p) for i, g in enumerate(groups)),
        key=lambda c: -c.strength,
    )
    for i, c in enumerate(clusters):
        c.cluster_id = i

    risk = combine(clusters, p)

    max_p = max(o.sif_probability for o in live)
    trend, delta = _trend(live, now, p)

    return SiteRisk(
        site_id=site,
        asof=now,
        site_risk=risk,
        level=level_for(risk, p),
        max_report_probability=max_p,
        escalation=risk - max_p,
        compounding=(risk >= p.review_threshold and max_p < p.review_threshold),
        clusters=clusters,
        n_observations=len(live),
        trend=trend,
        trend_delta=delta,
        params=p,
    )


def assess_all(observations: list[Observation], asof: datetime | None = None,
               params: RiskParams | None = None) -> list[SiteRisk]:
    """Every site represented in `observations`, highest risk first."""
    by_site: dict[str, list[Observation]] = {}
    for o in observations:
        by_site.setdefault(o.site_id, []).append(o)
    out = [assess_site(v, asof, params, site_id=k) for k, v in by_site.items()]
    return sorted(out, key=lambda r: -r.site_risk)


DEMO_SITE = "duliajan-rig-7"
DEMO = [
    (18, 0.31, "Gas detector at the welding bay was found with its calibration "
               "sticker three weeks out of date. Hot work was stopped and the unit swapped."),
    (11, 0.38, "Hot work permit was raised but the gas test reading was not written "
               "on it before the welder struck an arc."),
    (9, 0.45, "A scaffold plank on the north platform moved underfoot as a fitter "
              "stepped onto it at about 8 metres. He steadied himself on the handrail."),
    (4, 0.42, "Fitter working at height on the same platform had his harness lanyard "
              "clipped to the scaffold tube rather than to the anchor point."),
    (2, 0.36, "Crew began breaking the flange on the test line before the permit to "
              "work had come back signed."),
]

DEMO_QUIET = [
    (40, 0.22, "Housekeeping: cable reel left across the walkway near the store, moved aside."),
    (6, 0.19, "Printer in the HSE office ran out of toner during the morning shift."),
]


def _demo_observations(asof: datetime, score: bool = False) -> list[Observation]:
    from ml.store import sha1

    rows: list[Observation] = []
    for site, spec in ((DEMO_SITE, DEMO), ("moran-cpf", DEMO_QUIET)):
        for days_ago, p, text in spec:
            rows.append(Observation(
                obs_id=sha1(text)[:16],
                site_id=site,
                timestamp=asof - timedelta(days=days_ago),
                narrative=text,
                sif_probability=p,
                rules=_demo_rules(text),
            ))
    if score:
        from ml.predict import Scorer

        scorer = Scorer()
        print(scorer.describe())
        scores = scorer([r.narrative for r in rows])
        rows = [Observation(**{**asdict(r), "sif_probability": float(s)})
                for r, s in zip(rows, scores)]
    return rows


def _demo_rules(text: str) -> tuple[str, ...]:
    try:
        from ml.rules import get_matcher

        a = get_matcher().match(text)
        return tuple(m.rule_id for m in a.matched_rules[:2])
    except Exception:
        return ()


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Correlate a site's reports and flag compounding risk.")
    ap.add_argument("--site", help="assess one site from the store")
    ap.add_argument("--db", help="observation store (default data/observations.db)")
    ap.add_argument("--demo", action="store_true",
                    help="worked example on synthetic narratives; no store, no model")
    ap.add_argument("--score", action="store_true",
                    help="with --demo, score the demo narratives with the real model")
    ap.add_argument("--window", type=float, default=RiskParams.window_days)
    ap.add_argument("--half-life", type=float, default=RiskParams.half_life_days)
    ap.add_argument("--link-threshold", type=float, default=RiskParams.link_threshold)
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    params = RiskParams(window_days=args.window, half_life_days=args.half_life,
                        link_threshold=args.link_threshold)
    now = datetime.now(timezone.utc)

    if args.demo:
        obs = _demo_observations(now, score=args.score)
        if not args.json and not args.score:
            print("Synthetic narratives written for this repo. The probabilities are "
                  "illustrative,\nnot model output -- add --score to run the real model "
                  "over them.\n")
        results = assess_all(obs, now, params)
    else:
        import sqlite3

        from ml.store import Store

        try:
            with Store(args.db) as store:
                obs = store.observations(site_id=args.site,
                                         since_days=params.window_days, asof=now)
        except (OSError, sqlite3.Error) as exc:
            raise SystemExit(f"Cannot open the observation store: {exc}")
        if not obs:
            where = f" for site {args.site}" if args.site else ""
            raise SystemExit(
                f"No observations{where} in the last {int(params.window_days)} days.\n"
                "Record some first, or try `python -m ml.clustering --demo`.")
        results = assess_all(obs, now, params)

    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
        return

    for r in results:
        print("\n" + "=" * 78)
        print(r.explain())
    print("\n" + "=" * 78)
    print("Site risk is an aggregation policy, not a measured probability. Only the")
    print("per-report scores it combines are validated -- see docs/RESULTS.md.")


if __name__ == "__main__":
    main()
