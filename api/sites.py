"""api/sites.py -- the site-level layer, wired to the service"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

from api import audit
from ml.clustering import Observation, RiskParams, SiteRisk, assess_all, assess_site
from ml.store import Store

_STATE: dict = {"enabled": False, "status": "not configured", "db": None}


def configure() -> None:
    """Open the store once at startup to find out whether it works."""
    if os.getenv("SIF_STORE_ENABLED", "1").lower() in ("0", "false", "no"):
        _STATE.update(enabled=False, status="disabled by SIF_STORE_ENABLED", db=None)
        return
    try:
        with Store() as store:
            _STATE.update(enabled=True, db=str(store.path),
                          status=f"ok ({store.count()} observations)")
        audit.log(audit.ACCESS, "observation store ready", event="startup",
                  store=_STATE["db"], store_text=os.getenv("SIF_STORE_TEXT", "1"))
    except Exception as exc:
        _STATE.update(enabled=False, db=None,
                      status=f"FAILED: {type(exc).__name__}: {exc}")
        audit.log(audit.ACCESS, "observation store unavailable; site endpoints "
                  "will report 503 and scores will not be recorded",
                  level=logging.WARNING, event="startup_warning",
                  error=f"{type(exc).__name__}: {exc}")


def enabled() -> bool:
    return bool(_STATE["enabled"])


def status() -> str:
    return str(_STATE["status"])


def params(review_threshold: float | None = None) -> RiskParams:
    """Risk parameters from the environment."""
    def _f(name: str, default: float) -> float:
        try:
            return float(os.getenv(name, default))
        except ValueError:
            return default

    kw = dict(
        window_days=_f("SIF_SITE_WINDOW_DAYS", RiskParams.window_days),
        half_life_days=_f("SIF_SITE_HALF_LIFE_DAYS", RiskParams.half_life_days),
        link_threshold=_f("SIF_SITE_LINK_THRESHOLD", RiskParams.link_threshold),
    )
    if review_threshold is not None:
        kw["review_threshold"] = float(review_threshold)
    return RiskParams(**kw)


def normalise(narrative: str) -> tuple[str, dict | None]:
    """Returns (text the model should read, what changed) -- never raises."""
    try:
        from ml.ingest import normalise as _normalise

        result = _normalise(narrative)
        return result.text, (result.to_dict() if result.modified else None)
    except Exception as exc:
        audit.log(audit.ACCESS, "normalisation unavailable; scoring the report as "
                  "written", level=logging.WARNING, event="ingest_unavailable",
                  error=f"{type(exc).__name__}: {exc}")
        return narrative, None


def match_rules(narrative: str) -> list[dict]:
    """IOGP Life-Saving Rule matches, or nothing."""
    try:
        from ml.rules import get_matcher

        return [m.to_dict() for m in get_matcher().match(narrative).matched_rules]
    except Exception as exc:
        audit.log(audit.ACCESS, "rule matching unavailable", level=logging.WARNING,
                  event="rules_unavailable", error=f"{type(exc).__name__}: {exc}")
        return []


def record(rows: list[dict]) -> list[str | None]:
    """Record scored observations. Never raises."""
    if not enabled() or not rows:
        return [None] * len(rows)
    try:
        with Store() as store:
            return list(store.record_many(rows))
    except Exception as exc:
        audit.log(audit.AUDIT, "failed to record observations; scores were "
                  "returned but not stored", level=logging.ERROR,
                  event="store_write_failed", rows=len(rows),
                  error=f"{type(exc).__name__}: {exc}")
        return [None] * len(rows)


class StoreUnavailable(RuntimeError):
    """The site layer was asked for data it cannot reach."""


def _load(site_id: str | None, p: RiskParams, asof: datetime) -> list[Observation]:
    if not enabled():
        raise StoreUnavailable(status())
    try:
        with Store() as store:
            return store.observations(site_id=site_id, since_days=p.window_days,
                                      asof=asof)
    except Exception as exc:
        raise StoreUnavailable(f"{type(exc).__name__}: {exc}") from exc


def assess_one(site_id: str, review_threshold: float | None = None,
               asof: datetime | None = None) -> SiteRisk:
    p = params(review_threshold)
    now = asof or datetime.now(timezone.utc)
    return assess_site(_load(site_id, p, now), asof=now, params=p, site_id=site_id)


def assess_every(review_threshold: float | None = None,
                 asof: datetime | None = None) -> tuple[list[SiteRisk], RiskParams]:
    p = params(review_threshold)
    now = asof or datetime.now(timezone.utc)
    return assess_all(_load(None, p, now), asof=now, params=p), p


def audit_site(risk: SiteRisk, caller: str | None = None) -> None:
    """One audit line per site the operator was shown."""
    audit.log(
        audit.AUDIT, "site assessment", event="site_assessment",
        site_id=risk.site_id, site_risk=round(risk.site_risk, 6),
        site_level=risk.level,
        compounding=risk.compounding, escalation=round(risk.escalation, 6),
        max_report_probability=round(risk.max_report_probability, 6),
        n_observations=risk.n_observations, n_clusters=len(risk.clusters),
        trend=risk.trend, asof=risk.asof.isoformat(),
        window_days=risk.params.window_days,
        half_life_days=risk.params.half_life_days,
        review_threshold=risk.params.review_threshold,
        caller=caller,
    )
