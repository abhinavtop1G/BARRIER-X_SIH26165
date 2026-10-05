# api/ — FastAPI scoring service

Serves the SIF-potential classifier. Loads the checkpoint named in
`model_artifacts/SERVING.json`, preferring its ONNX int8 export (172 MB,
~30 ms/doc on CPU, no GPU needed) and falling back to PyTorch if no export is
present.

## Run

```bash
pip install fastapi "uvicorn[standard]"
uvicorn api.main:app --reload --port 8000
```

Interactive docs: http://localhost:8000/docs

## Endpoints

| method | path | purpose |
|---|---|---|
| POST | `/score` | one narrative |
| POST | `/score/batch` | up to 500, returned highest-risk first |
| GET | `/sites` | site risk queue, highest first; `?alerting_only=true` for compounding sites |
| GET | `/sites/{site_id}` | one site in full: hazard groups, evidence, explanation |
| GET | `/dashboard` | the safety officer's workspace (HTML) |
| GET | `/health` | model backend, checkpoint, calibration, threshold, readiness, store |
| GET | `/` | service info |

### Example

```bash
curl -X POST http://localhost:8000/score \
  -H "Content-Type: application/json" \
  -d '{"narrative":"While rigging down, the worker stood under a suspended load when the sling parted and the load fell to the deck."}'
```

The response carries the checkpoint and calibration that produced the score, so
a stored result can be traced back to the model version months later:

```json
{
  "narrative": "While rigging down, ...",
  "sif_probability": 0.8123,
  "threshold": 0.4471,
  "flagged": true,
  "band": "HIGH",
  "guidance": "Review first. Strong indicators of serious-injury potential.",
  "model": "seed0",
  "calibration": "platt"
}
```

Run `python -m ml.selftest` for the live numbers on your checkpoint rather than
trusting the example above — it is illustrative, and the threshold in particular
is per-checkpoint.

## Why the response is not a boolean

The model is a ranker trained on 231 labelled rows. A bare yes/no would claim
more certainty than it has and would leave a reviewer unable to tell a marginal
call from a confident one. Four bands:

| band | meaning |
|---|---|
| HIGH | ≥ threshold + margin — review first |
| ELEVATED | ≥ threshold — flag for review |
| BORDERLINE | within margin below threshold — model is unsure |
| LOW | below that — no action indicated |

The band function lives in `ml/predict.py` and is **imported** here rather than
restated. It used to be defined in both places with different margins (0.03
there, 0.15 here), and because the uncalibrated model's scores spanned only 0.06,
`HIGH` and `LOW` were arithmetically unreachable in this service: every report
came back `ELEVATED` or `BORDERLINE` regardless of content. One definition now,
and `ml/selftest.py` asserts both modules share it.

`/score/batch` returns highest-risk first. **That ordering is the product** — an
HSE reviewer works a finite queue per shift.

## Threshold, and when not to trust it

A policy dial, not a model constant. It is selected on validation (never on
test), stored in the serving checkpoint's `run_meta.json`, and overridable per
request or via the `SIF_THRESHOLD` environment variable.

**An absolute threshold assumes incoming reports resemble the validation split.**
They may not — the labelled data is Brazilian mining, the deployment target is
oil and gas. When the distribution shifts, every score shifts with it and a fixed
cut-off flags everything or nothing. This is not hypothetical: before
calibration, the shipped threshold flagged **zero of six** realistic oil-and-gas
severe narratives.

For out-of-domain batches use `top_frac` instead:

```bash
curl -X POST http://localhost:8000/score/batch \
  -H "Content-Type: application/json" \
  -d '{"narratives":["...","..."], "top_frac": 0.15}'
```

That flags the top 15% of whatever batch arrives, by rank. It is what "a reviewer
works 20 reports a shift" actually means, and it is immune to a shift in the
absolute scale. The response's `flagging_rule` says which rule was applied.

## Site history and `/sites`

Per-report triage cannot see that a site has four dull problems at once. Pass a
`site_id` and the score is recorded against that site's history; `/sites` then
ranks places rather than reports.

```bash
curl -X POST http://localhost:8000/score \
  -H "Content-Type: application/json" \
  -d '{"narrative":"A scaffold plank moved underfoot at 8 metres.",
       "site_id":"duliajan-rig-7","occurred_at":"2026-09-01T06:30:00Z"}'
```

The response gains `recorded`, `obs_id` and `rules` — the IOGP Life-Saving Rules
the wording touches, the phrases that triggered each match, and the commitments a
reviewer should check. Those are deterministic keyword matches from
`ml/rules.py`, so `confidence` is wording similarity and **not** a risk level;
`sif_probability` is the risk number and the two are deliberately separate.

`/score/batch` takes `site_id` for a single-site batch or `sites` for a mixed
ingest (same length as `narratives`; a mismatch is a 422 rather than a silently
truncated write). Results are still returned ranked by risk, and each site stays
with the narrative it arrived on.

```bash
curl 'http://localhost:8000/sites?alerting_only=true'
curl  http://localhost:8000/sites/duliajan-rig-7
```

`compounding: true` is the alert worth acting on — the site clears the review
threshold although none of its individual reports did. `/sites/{site_id}` adds
the hazard clusters, the reports behind each, and an `explanation` templated from
those numbers so every claim in it can be checked against the response body.

**These are not the same kind of number as `/score`.** A per-report probability
is calibrated and measured on a frozen test set; a site risk is an aggregation
policy with no ground truth behind it, and it inherits and amplifies the
per-report model's out-of-domain errors. Every site response carries its
parameters and a `caveat` field saying so. See `ml/clustering.py`.

**Recording can never break scoring.** If the store is missing, locked or
unwritable, `/score` still returns a valid score with `recorded: false`, `/sites`
returns 503 with the reason, and `/health` reports `store_enabled: false`. The
store holds narrative text by design — clustering needs it for lexical
similarity, which is a deliberate departure from the audit log's hashing — so
`SIF_STORE_TEXT=0` keeps hashes and rule ids only, and clustering falls back to
rule overlap alone. Treat the database as holding the same class of data as the
incident system it mirrors.

To load history with a timestamp per report (seeding a demo, backfilling a
backlog), write through `ml/store.py` directly rather than through the API —
`occurred_at` applies to a whole batch.

## Dashboard

`GET /dashboard` serves a single self-contained HTML file — no build step, no
CDN, no framework — so it works offline, inside the container, and on whatever
network the operator is actually on.

Left is the shift queue: sites ranked by risk, compounding ones called out
above it. Right is why — the hazard groups behind the score, the reports behind
each group, and the IOGP rules behind each report. A second tab scores a fresh
narrative and, if given a site, files it. It polls `/sites` every 15 seconds;
that is polling, not push, and the page says so next to the timestamp.

The page is a static shell: it renders nothing server-side and holds no incident
data, which is why it is exempt from auth alongside `/docs`. Every request it
then makes is authenticated normally, and it will prompt for a key on the first
401 and keep it in `sessionStorage` (not `localStorage` — it is a credential on
what may be a shared terminal).

Two things it deliberately says out loud. The caveat bar states that per-report
scores are a ranker and site risk is an unvalidated policy — `api/README.md`
already asked for these to be surfaced in the UI rather than buried, and there
is a test asserting they are still on screen. And when a report scores below the
threshold *but* matches a Life-Saving Rule, the page flags the disagreement
instead of leaving "No action indicated by the model" to stand alone: the served
model scores an expired-gas-test vessel entry at 0.28, which is the §5f
threshold failure, and a low score is not a clearance.

## Authentication

**Off unless `SIF_API_KEYS` is set.** Failing open is the wrong default for
production and the right one for a demo someone else has to start, so the
compromise is that it fails open *loudly*: the startup log warns, and
`/health` reports `auth_enabled: false`.

```bash
SIF_API_KEYS=key-one,key-two uvicorn api.main:app --port 8000

curl -H 'X-API-Key: key-one'          ...   # or
curl -H 'Authorization: Bearer key-one' ...
```

Keys are compared as SHA-256 digests, so the comparison never touches the raw
secret. Logs record a 12-character key id, never the key. `/health`, `/`,
`/docs` and `/openapi.json` stay reachable without one so orchestrators can
probe.

## Rate limiting

Token bucket per caller — per API key, or per client IP when auth is off.
`SIF_RATE_LIMIT` requests per minute (default 60, `0` disables) with
`SIF_RATE_BURST` headroom (default 20). Over the limit returns **429** with a
`Retry-After` header.

**Counted per process.** With N replicas the effective limit is N times the
configured rate. If you scale out, move this to shared state or enforce it at
the ingress.

## Audit trail

Every prediction emits one JSON line carrying the score, the operating point it
was judged against, and a content hash of the weights that produced it — which
is what makes "why was this report not flagged?" answerable months later.

```json
{"ts":"2026-09-08T13:59:30.033Z","level":"INFO","logger":"avertx.audit",
 "request_id":"dde6f4f2bcc14aab","event":"prediction",
 "narrative_sha256":"f37f73a1...","narrative_chars":86,
 "sif_probability":0.373266,"threshold":0.302736,"band":"HIGH","flagged":true,
 "flagging_rule":"threshold","latency_ms":16.06,
 "model_checkpoint":"seed2","model_fingerprint":"e3b1a0f55a1633f9",
 "model_calibration":"platt","caller":"anon:127.0.0.1"}
```

**Narrative text is hashed, not stored, by default.** Incident narratives name
people and sites, and an audit log is usually retained longer and read more
widely than the reports themselves. The hash proves which input produced which
score, which is what an audit needs. Set `SIF_AUDIT_TEXT=1` when your retention
policy actually allows the text.

Every request also gets an `X-Request-ID`, echoed on the response. An inbound
one is honoured, so a trace started upstream survives into the audit trail.

## Configuration

| variable | default | effect |
|---|---|---|
| `SIF_MODEL_DIR` | `SERVING.json` | override the checkpoint |
| `SIF_THRESHOLD` | from `run_meta.json` | override the review threshold |
| `SIF_API_KEYS` | *(unset)* | comma-separated keys; unset means **no auth** |
| `SIF_RATE_LIMIT` | `60` | requests/min per caller, `0` disables |
| `SIF_RATE_BURST` | `20` | burst headroom above the rate |
| `SIF_AUDIT_LOG` | *(stdout only)* | also append audit records to this file |
| `SIF_AUDIT_TEXT` | `0` | `1` records narrative text in the audit log |
| `SIF_STORE_ENABLED` | `1` | `0` turns the site layer off; `/sites` then 503s |
| `SIF_STORE_DB` | `data/observations.db` | where site history lives |
| `SIF_STORE_TEXT` | `1` | `0` stores hashes only; clustering falls back to rule overlap |
| `SIF_SITE_WINDOW_DAYS` | `90` | how far back a site assessment looks |
| `SIF_SITE_HALF_LIFE_DAYS` | `30` | time decay on an observation's score |
| `SIF_SITE_LINK_THRESHOLD` | `0.30` | similarity cut height for hazard clustering |
| `SIF_LOG_LEVEL` | `INFO` | |
| `SIF_WORKERS` | `1` | each worker holds its own ~570 MB copy of the model |
| `ALLOWED_ORIGINS` | `*` | CORS allowlist, comma separated |

## Tests

```bash
pip install -r requirements-dev.txt
pytest -m "not model"     # 116 tests, no model needed
pytest                    # all 139, needs `python -m ml.fetch_model` first
```

`.github/workflows/ci.yml` runs the first on every push across Python 3.11 and
3.12, and the second in a job that fetches and caches the model.

## Before this faces anything real

- **CORS lock-down** — set `ALLOWED_ORIGINS`, currently `*`
- **Rate limiting across replicas** — currently per process
- **Log shipping and retention** — records go to stdout; decide where they live
  and for how long before you turn on `SIF_AUDIT_TEXT`
- **Key rotation** — keys come from the environment; there is no revocation list

Authentication, rate limiting, request logging, the prediction audit trail and
model version in the response were the earlier items on this list, and are done.

## Limitations worth surfacing in the UI

Trained on Brazilian mining and metals incidents, with supervised intermediate
training on US hazmat transport incidents; the deployment target is oil and gas.
Transfer to wellsite narratives is untested. The service ranks reports for human
review and does not replace human judgement.
