"""api/schemas.py -- request and response shapes."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Band = Literal["HIGH", "ELEVATED", "BORDERLINE", "LOW"]
SiteLevel = Literal["CRITICAL", "HIGH", "WATCH", "NORMAL"]

SITE_ID = Field(
    None, max_length=200,
    description="Where this happened. Supplying it records the score against the "
                "site's history, so /sites can correlate it with other reports "
                "from the same place. Omit it and nothing is stored.",
)


class ScoreRequest(BaseModel):
    narrative: str = Field(
        ...,
        min_length=10,
        max_length=8000,
        description="Free-text incident or near-miss narrative.",
        json_schema_extra={
            "example": "While rigging down, the worker stood under a suspended "
            "load when the sling parted and the load fell to the deck."
        },
    )
    threshold: float | None = Field(
        None, ge=0.0, le=1.0,
        description="Override the review threshold. Lower catches more true SIF "
                    "cases at the cost of more false alarms.",
    )
    site_id: str | None = SITE_ID
    occurred_at: datetime | None = Field(
        None,
        description="When the incident happened, if not now. Drives time decay in "
                    "the site assessment. Naive timestamps are read as UTC.",
    )
    reported_by: str | None = Field(None, max_length=200)
    normalise: bool = Field(
        False,
        description="Run the report through ml/ingest.py first: transliterate "
                    "Devanagari/Assamese, expand oilfield abbreviations, map "
                    "romanised Hindi/Assamese to English, repair domain typos. "
                    "Off by default because it changes what the model reads and "
                    "the measured benefit is not resolvable on 10 probe pairs "
                    "(docs/RESULTS.md 5g); the response reports every "
                    "substitution it made.",
    )


class BatchScoreRequest(BaseModel):
    narratives: list[str] = Field(..., min_length=1, max_length=500)
    threshold: float | None = Field(None, ge=0.0, le=1.0)
    top_frac: float | None = Field(
        None, gt=0.0, le=1.0,
        description="Flag the top fraction of THIS batch by rank instead of by "
                    "absolute threshold (e.g. 0.15 for the top 15%). Robust to "
                    "domain shift; prefer it when the reports may not resemble "
                    "the validation split.",
    )
    sort: bool = Field(True, description="Return highest-risk first - the triage queue order.")
    site_id: str | None = SITE_ID
    sites: list[str] | None = Field(
        None,
        description="Per-narrative sites, for a mixed ingest. Must be the same "
                    "length as `narratives`. Use `site_id` instead when the whole "
                    "batch is from one place.",
    )
    occurred_at: datetime | None = Field(
        None, description="Applies to the whole batch. To load history with a "
                          "timestamp per report, write through ml/store.py.")
    reported_by: str | None = Field(None, max_length=200)
    normalise: bool = Field(
        False,
        description="Run the report through ml/ingest.py first: transliterate "
                    "Devanagari/Assamese, expand oilfield abbreviations, map "
                    "romanised Hindi/Assamese to English, repair domain typos. "
                    "Off by default because it changes what the model reads and "
                    "the measured benefit is not resolvable on 10 probe pairs "
                    "(docs/RESULTS.md 5g); the response reports every "
                    "substitution it made.",
    )

    @model_validator(mode="after")
    def _sites_line_up(self) -> "BatchScoreRequest":
        if self.sites is not None:
            if self.site_id is not None:
                raise ValueError("pass either site_id or sites, not both")
            if len(self.sites) != len(self.narratives):
                raise ValueError(
                    f"sites has {len(self.sites)} entries but narratives has "
                    f"{len(self.narratives)}; they must line up")
        return self


class RuleMatch(BaseModel):
    """An IOGP Life-Saving Rule the narrative appears to touch."""

    rule_id: str
    rule_name: str
    action: str
    confidence: float = Field(
        ..., description="wording similarity to the rule, NOT a risk level")
    evidence: list[str] = Field(..., description="the phrases that triggered the match")
    suggested_checks: list[str]
    source: str


class ScoreResponse(BaseModel):
    narrative: str
    sif_probability: float = Field(
        ..., description="Calibrated P(this incident had serious-injury potential)")
    threshold: float
    flagged: bool = Field(..., description="probability >= threshold, or within top_frac by rank")
    band: Band
    guidance: str
    model: str = Field(..., description="checkpoint that produced this score")
    calibration: str = Field(..., description="calibration method applied (platt/isotonic/identity)")
    model_fingerprint: str = Field(
        ..., description="content hash of the served weights. Ties a stored score to "
                         "the exact file that produced it, which a checkpoint name "
                         "alone cannot do once a name is reused.")
    rules: list[RuleMatch] = Field(
        default_factory=list,
        description="Which Life-Saving Rules the wording touches, and what a "
                    "reviewer should check. Empty is not a safety judgement - read "
                    "sif_probability, which is independent of this.")
    site_id: str | None = None
    recorded: bool = Field(
        False,
        description="Whether this score was written to the site history. False "
                    "with a site_id supplied means the store was unavailable - the "
                    "score is still valid, /health says why.")
    obs_id: str | None = Field(
        None, description="Identifier of the stored observation, for joining back "
                          "to a site assessment.")
    normalisation: dict | None = Field(
        None,
        description="Present when `normalise` was requested and changed the text: "
                    "the original, what the model actually read, and every "
                    "substitution with the step that made it. Rewriting an "
                    "incident report before a safety decision is made on it is "
                    "not a step that gets to be invisible.")


class BatchScoreResponse(BaseModel):
    results: list[ScoreResponse]
    count: int
    flagged_count: int
    threshold: float
    flagging_rule: str = Field(..., description="how `flagged` was decided for this batch")


SITE_CAVEAT = (
    "Site risk is an aggregation policy over validated per-report scores, not a "
    "measured probability. It has no test set behind it and no PR-AUC, it assumes "
    "hazards at a site are independent when they are not, and it inherits and "
    "amplifies the per-report model's out-of-domain errors. Read the clusters and "
    "their evidence, not the number alone."
)


class ObservationOut(BaseModel):
    obs_id: str
    timestamp: str
    sif_probability: float
    rules: list[str]
    narrative: str = Field(
        "", description="Empty when the store is running with SIF_STORE_TEXT=0.")


class ClusterOut(BaseModel):
    """One hazard at a site, and every report of it inside the window."""

    cluster_id: int
    label: str
    rule_ids: list[str]
    size: int
    peak: float = Field(..., description="strongest member score after time decay")
    effective_count: float = Field(
        ..., description="report count once decay is applied; 3 stale reports "
                         "count for less than 2 fresh ones")
    recurrence_bonus: float = Field(
        ..., description="how much repetition added on top of `peak`")
    strength: float = Field(..., description="what this hazard contributes to site risk")
    latest: str
    peak_obs_id: str
    members: list[ObservationOut]


class SiteSummary(BaseModel):
    """A row in the operator's queue."""

    site_id: str
    site_risk: float
    level: SiteLevel
    guidance: str
    compounding: bool = Field(
        ..., description="True when the site clears the review threshold and none "
                         "of its individual reports did. This is the alert.")
    escalation: float = Field(
        ..., description="site_risk minus the highest single report score. Positive "
                         "means the accumulation is doing the work.")
    max_report_probability: float
    n_observations: int
    n_clusters: int
    trend: str = Field(..., description="rising / steady / falling / insufficient history")
    trend_delta: float
    top_hazards: list[str]
    asof: str


class SiteRiskResponse(SiteSummary):
    """A site in full: every hazard group, its evidence, and the reasoning."""

    clusters: list[ClusterOut]
    explanation: str = Field(
        ..., description="Plain-language summary of why this site scores as it "
                         "does. Templated from the numbers above, not generated.")
    params: dict = Field(
        ..., description="The policy constants this assessment used. Recorded "
                         "because they are tunable at runtime and the assessment "
                         "cannot be re-derived without them.")
    caveat: str = SITE_CAVEAT


class SitesResponse(BaseModel):
    sites: list[SiteSummary]
    count: int
    alerting_count: int = Field(..., description="how many are compounding")
    window_days: float
    review_threshold: float
    asof: str
    caveat: str = SITE_CAVEAT


class HealthResponse(BaseModel):
    status: str
    model_backend: str
    model: str
    model_fingerprint: str
    calibration: str
    default_threshold: float
    band_margin: float
    model_ready: bool
    store_enabled: bool = Field(
        False, description="Whether scores are being recorded to site history. "
                           "False means /sites is unavailable and scoring is "
                           "unaffected.")
    store_status: str = Field(
        "not configured",
        description="Why, when store_enabled is false.")
    auth_enabled: bool = Field(
        ..., description="False means anyone who can reach this service can score. "
                         "Set SIF_API_KEYS to enable authentication.")
    rate_limit_per_min: float = Field(
        ..., description="Per-caller limit, counted per process. With N replicas the "
                         "effective limit is N times this.")
