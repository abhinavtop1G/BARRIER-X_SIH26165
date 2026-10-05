"""api/main.py -- FastAPI service for SIF-potential scoring."""

from __future__ import annotations

import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api import audit, security, sites  # noqa: E402
from api.schemas import (  # noqa: E402
    BatchScoreRequest,
    BatchScoreResponse,
    HealthResponse,
    ScoreRequest,
    ScoreResponse,
    SiteRiskResponse,
    SitesResponse,
    SiteSummary,
)
from ml.clustering import LEVEL_GUIDANCE as CLUSTER_GUIDANCE  # noqa: E402
from ml.predict import GUIDANCE, band  # noqa: E402

STATE: dict = {
    "scorer": None, "threshold": 0.5, "margin": 0.15,
    "backend": "not loaded", "model": "not loaded", "calibration": "none",
    "fingerprint": "unknown", "source": "unknown", "limiter": None,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    from ml.predict import Scorer

    audit.configure()
    STATE["limiter"] = security.build_limiter()
    sites.configure()

    try:
        scorer = Scorer(os.getenv("SIF_MODEL_DIR") or None)
        env_thr = os.getenv("SIF_THRESHOLD")
        thr, why = scorer.threshold(float(env_thr) if env_thr else None)

        onnx = next((p for p in (scorer.ckpt / "onnx").glob("*.onnx")), None)
        fingerprint = audit.model_fingerprint(onnx) if onnx else "pytorch"

        STATE.update(
            scorer=scorer, threshold=thr, margin=scorer.band_margin,
            backend=scorer.backend, model=str(scorer.ckpt),
            calibration=scorer.calibrator.method, fingerprint=fingerprint,
            source=scorer.meta.get("source", "unknown"),
        )
        audit.log(audit.ACCESS, "model ready", event="startup",
                  backend=scorer.backend, checkpoint=str(scorer.ckpt),
                  model_fingerprint=fingerprint, calibration=scorer.calibrator.method,
                  threshold=round(thr, 6), threshold_reason=why,
                  band_margin=round(scorer.band_margin, 6),
                  calibrated=scorer.calibrated)
        if not scorer.calibrated:
            audit.log(audit.ACCESS, "no calibration found; probabilities are raw model "
                      "output and bands may not be meaningful",
                      level=logging.WARNING, event="startup_warning")
        if not security.auth_enabled():
            audit.log(audit.ACCESS, "SIF_API_KEYS is not set: this service is "
                      "UNAUTHENTICATED and will score for anyone who can reach it",
                      level=logging.WARNING, event="startup_warning")
    except Exception as exc:
        STATE["backend"] = f"FAILED: {exc}"
        audit.log(audit.ACCESS, "model failed to load", level=logging.ERROR,
                  event="startup_failure", error=f"{type(exc).__name__}: {exc}")
    yield
    STATE["scorer"] = None


app = FastAPI(
    title="BARRIER X - SIF Potential Scoring",
    description=(
        "Scores incident and near-miss narratives for **SIF potential**: could "
        "this have caused a Serious Injury or Fatality, regardless of what "
        "actually happened?\n\n"
        "Trained on 231 labelled reports, with domain-adaptive pretraining over "
        "590K unlabelled safety narratives and supervised intermediate training "
        "on 73K PHMSA serious-incident determinations. **This is a triage aid "
        "that ranks reports for human review - it does not replace human "
        "judgement.**\n\n"
        "Probabilities are calibrated on a held-out validation split. For "
        "out-of-domain batches prefer `top_frac` on `/score/batch` over the "
        "absolute threshold."
    ),
    version="2.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("ALLOWED_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def access_log(request: Request, call_next):
    """Tag every request with an id and time it."""
    rid = request.headers.get("x-request-id") or audit.new_request_id()
    token = audit.request_id_var.set(rid)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        audit.log(audit.ACCESS, "unhandled error", level=logging.ERROR,
                  event="request", method=request.method, path=request.url.path,
                  latency_ms=round((time.perf_counter() - started) * 1000, 2))
        audit.request_id_var.reset(token)
        raise
    latency = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = rid
    if request.url.path not in ("/health",):
        audit.log(audit.ACCESS, "request", event="request", method=request.method,
                  path=request.url.path, status=response.status_code,
                  latency_ms=round(latency, 2))
    audit.request_id_var.reset(token)
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Denials are audit events, not just responses."""
    if exc.status_code in (401, 403, 429):
        audit.log(audit.ACCESS, "request denied", level=logging.WARNING,
                  event="denied", status=exc.status_code, path=request.url.path,
                  reason=str(exc.detail))
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code,
                        headers=exc.headers)


def require_caller(request: Request) -> str:
    """Authenticate, then spend a rate-limit token. Order matters: an unauthenticated"""
    if request.url.path in security.EXEMPT_PATHS:
        return "exempt"
    caller = security.authenticate(request)
    security.enforce(STATE["limiter"], caller)
    return caller


def _require_model():
    if STATE["scorer"] is None:
        raise HTTPException(status_code=503, detail=f"Model not loaded: {STATE['backend']}")


def _model_stamp() -> dict:
    return {
        "checkpoint": Path(STATE["model"]).name,
        "fingerprint": STATE["fingerprint"],
        "calibration": STATE["calibration"],
    }


def _response(text: str, p: float, thr: float,
              rules: list[dict] | None = None) -> ScoreResponse:
    b = band(p, thr, STATE["margin"])
    return ScoreResponse(
        narrative=text,
        sif_probability=round(float(p), 4),
        threshold=round(thr, 4),
        flagged=bool(p >= thr),
        band=b,
        guidance=GUIDANCE[b],
        model=Path(STATE["model"]).name,
        calibration=STATE["calibration"],
        model_fingerprint=STATE["fingerprint"],
        rules=rules or [],
    )


def _summary(risk) -> SiteSummary:
    return SiteSummary(
        site_id=risk.site_id,
        site_risk=round(risk.site_risk, 4),
        level=risk.level,
        guidance=CLUSTER_GUIDANCE[risk.level],
        compounding=risk.compounding,
        escalation=round(risk.escalation, 4),
        max_report_probability=round(risk.max_report_probability, 4),
        n_observations=risk.n_observations,
        n_clusters=len(risk.clusters),
        trend=risk.trend,
        trend_delta=round(risk.trend_delta, 4),
        top_hazards=[c.label for c in risk.contributing[:3]],
        asof=risk.asof.isoformat(),
    )


@app.get("/health", response_model=HealthResponse, tags=["ops"])
def health() -> HealthResponse:
    return HealthResponse(
        status="ok" if STATE["scorer"] is not None else "degraded",
        model_backend=STATE["backend"],
        model=STATE["model"],
        model_fingerprint=STATE["fingerprint"],
        calibration=STATE["calibration"],
        default_threshold=round(STATE["threshold"], 4),
        band_margin=round(STATE["margin"], 4),
        model_ready=STATE["scorer"] is not None,
        store_enabled=sites.enabled(),
        store_status=sites.status(),
        auth_enabled=security.auth_enabled(),
        rate_limit_per_min=float(os.getenv("SIF_RATE_LIMIT", "60")),
    )


@app.post("/score", response_model=ScoreResponse, tags=["scoring"])
def score(req: ScoreRequest, caller: str = Depends(require_caller)) -> ScoreResponse:
    """Score a single narrative."""
    _require_model()
    thr = req.threshold if req.threshold is not None else STATE["threshold"]

    text, norm = sites.normalise(req.narrative) if req.normalise else (req.narrative, None)

    t0 = time.perf_counter()
    p = float(STATE["scorer"]([text])[0])
    latency = (time.perf_counter() - t0) * 1000

    rules = sites.match_rules(text)
    out = _response(req.narrative, p, thr, rules)
    out.site_id = req.site_id
    out.normalisation = norm

    if req.site_id:
        obs_id = sites.record([dict(
            site_id=req.site_id, narrative=text, sif_probability=p,
            timestamp=req.occurred_at, rules=[r["rule_id"] for r in rules],
            band=out.band, model=Path(STATE["model"]).name,
            model_fingerprint=STATE["fingerprint"], reported_by=req.reported_by,
        )])[0]
        out.obs_id, out.recorded = obs_id, obs_id is not None

    audit.prediction_record(
        narrative=req.narrative, probability=p, threshold=thr, band=out.band,
        flagged=out.flagged, model=_model_stamp(), latency_ms=latency, caller=caller,
        site_id=req.site_id, obs_id=out.obs_id,
        rules=[r["rule_id"] for r in rules],
        normalised=bool(norm),
    )
    return out


@app.post("/score/batch", response_model=BatchScoreResponse, tags=["scoring"])
def score_batch(req: BatchScoreRequest,
                caller: str = Depends(require_caller)) -> BatchScoreResponse:
    """Score many narratives. Returned highest-risk first by default - that"""
    _require_model()
    thr = req.threshold if req.threshold is not None else STATE["threshold"]

    if req.normalise:
        pairs = [sites.normalise(t) for t in req.narratives]
        texts = [t for t, _ in pairs]
        norms = [n for _, n in pairs]
    else:
        texts, norms = list(req.narratives), [None] * len(req.narratives)

    t0 = time.perf_counter()
    probs = [float(p) for p in STATE["scorer"](texts)]
    latency = (time.perf_counter() - t0) * 1000

    ranked = sorted(
        ((p, i, t) for i, (t, p) in enumerate(zip(req.narratives, probs))),
        key=lambda x: x[0], reverse=True,
    )

    rule = f"probability >= {thr:.4f}"
    k = len(ranked)
    if req.top_frac:
        k = max(1, int(round(len(ranked) * req.top_frac)))
        rule = f"top {req.top_frac:.0%} of this batch by rank ({k} of {len(ranked)})"

    site_of = dict(enumerate(req.sites)) if req.sites else {}

    out = []
    for rank, (p, i, t) in enumerate(ranked):
        r = _response(t, p, thr, sites.match_rules(texts[i]))
        r.site_id = site_of.get(i, req.site_id)
        r.normalisation = norms[i]
        if req.top_frac:
            r.flagged = rank < k
        out.append((i, r))

    to_store = [(i, r) for i, r in out if r.site_id]
    if to_store:
        obs_ids = sites.record([dict(
            site_id=r.site_id, narrative=texts[i], sif_probability=r.sif_probability,
            timestamp=req.occurred_at, rules=[m.rule_id for m in r.rules],
            band=r.band, model=Path(STATE["model"]).name,
            model_fingerprint=STATE["fingerprint"], reported_by=req.reported_by,
        ) for i, r in to_store])
        for (_, r), obs_id in zip(to_store, obs_ids):
            r.obs_id, r.recorded = obs_id, obs_id is not None

    per_doc = latency / max(len(ranked), 1)
    stamp = _model_stamp()
    for _, r in out:
        audit.prediction_record(
            narrative=r.narrative, probability=r.sif_probability, threshold=thr,
            band=r.band, flagged=r.flagged, model=stamp, latency_ms=per_doc,
            rule="top_frac" if req.top_frac else "threshold", caller=caller,
            site_id=r.site_id, obs_id=r.obs_id,
            rules=[m.rule_id for m in r.rules],
            normalised=bool(r.normalisation),
        )

    results = [r for _, r in (out if req.sort else sorted(out, key=lambda x: x[0]))]
    return BatchScoreResponse(
        results=results,
        count=len(results),
        flagged_count=sum(r.flagged for r in results),
        threshold=round(thr, 4),
        flagging_rule=rule,
    )


def _require_store():
    """503 with the reason, mirroring how a missing model is reported."""
    if not sites.enabled():
        raise HTTPException(status_code=503,
                            detail=f"Site history unavailable: {sites.status()}")


@app.get("/sites", response_model=SitesResponse, tags=["sites"])
def list_sites(alerting_only: bool = False,
               caller: str = Depends(require_caller)) -> SitesResponse:
    """The operator's queue: every site with recent reports, highest risk first."""
    _require_store()
    try:
        results, p = sites.assess_every(STATE["threshold"])
    except sites.StoreUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Site history unavailable: {exc}")

    alerting = [r for r in results if r.compounding]
    shown = alerting if alerting_only else results

    audit.log(audit.AUDIT, "site queue", event="site_queue", caller=caller,
              sites=len(results), alerting=len(alerting),
              alerting_only=alerting_only, window_days=p.window_days,
              review_threshold=p.review_threshold)
    for r in alerting:
        sites.audit_site(r, caller)

    return SitesResponse(
        sites=[_summary(r) for r in shown],
        count=len(shown),
        alerting_count=len(alerting),
        window_days=p.window_days,
        review_threshold=round(p.review_threshold, 4),
        asof=(results[0].asof if results else datetime.now(timezone.utc)).isoformat(),
    )


@app.get("/sites/{site_id}", response_model=SiteRiskResponse, tags=["sites"])
def site_detail(site_id: str, caller: str = Depends(require_caller)) -> SiteRiskResponse:
    """One site in full: every hazard group, the reports behind it, and why."""
    _require_store()
    try:
        risk = sites.assess_one(site_id, STATE["threshold"])
    except sites.StoreUnavailable as exc:
        raise HTTPException(status_code=503, detail=f"Site history unavailable: {exc}")

    if risk.n_observations == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No reports for site {site_id!r} in the last "
                   f"{int(risk.params.window_days)} days.")

    sites.audit_site(risk, caller)
    d = risk.to_dict()
    return SiteRiskResponse(
        **_summary(risk).model_dump(),
        clusters=d["clusters"],
        explanation=d["explanation"],
        params=d["params"],
    )


DASHBOARD = Path(__file__).resolve().parent / "static" / "dashboard.html"


@app.get("/dashboard", response_class=HTMLResponse, tags=["ops"],
         include_in_schema=False)
def dashboard() -> HTMLResponse:
    """The safety officer's workspace."""
    if not DASHBOARD.exists():
        raise HTTPException(status_code=503,
                            detail=f"Dashboard not installed: {DASHBOARD} is missing.")
    return HTMLResponse(DASHBOARD.read_text(encoding="utf-8"))


@app.get("/", tags=["ops"])
def root() -> dict:
    return {
        "service": "BARRIER X SIF scoring",
        "docs": "/docs",
        "dashboard": "/dashboard",
        "endpoints": ["/score", "/score/batch", "/sites", "/sites/{site_id}",
                      "/dashboard", "/health"],
    }
