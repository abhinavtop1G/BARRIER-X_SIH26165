# BARRIER X

**AI/NLP engine to detect Serious Injury & Fatality (SIF) precursors in Oil India's
unsafe-act, unsafe-condition and near-miss reports.**

| | |
|---|---|
| Event | Smart India Hackathon 2026 |
| Problem statement | SIH26165 (Oil India Limited, HSSE) |
| Theme / category | Smart Automation / Software |
| Team | **GIT PUSH AND PRAY** |

Given an incident or near-miss narrative, the model estimates **SIF potential**:
could this have caused a Serious Injury or Fatality, regardless of what actually
happened?

The system has five services: a React frontend, a Go API gateway, the ML scoring
service, an AI HSE agent and MongoDB. This README covers the ML scoring service,
its dashboard at `/dashboard`, and the training pipeline. `POST /score` scores one
report and `GET /sites` returns the site queue.

A 90-second explainer video and the trained model are attached to the
[Releases](https://github.com/abhinavtop1G/BARRIER-X_SIH26165/releases) page.
The story of how we built it, including what failed and where we want to take it
next, is in [`docs/article.md`](docs/article.md). For a short overview of the
whole project, see [`docs/summary.md`](docs/summary.md).

```bash
pip install -r requirements-serve.txt
python -m ml.fetch_model            # 531 MB, checksum-verified
uvicorn api.main:app --port 8000
```

That is this service alone; setting up the full four-service product around it —
React frontend, Go gateway, AI HSE agent — is [`SETUP.md`](SETUP.md).

---

## Where it stands

| | |
|---|---|
| Frozen test set | 123 held-out narratives, base rate 0.407 |
| **PR-AUC** | **0.6667** (3-seed mean 0.6782 ±0.027) |
| **ROC-AUC** | **0.7570** (3-seed mean 0.7528 ±0.004) |
| precision / recall / F1 | 0.5443 / 0.8600 / 0.6667 |
| P@10 / P@20 | 0.800 / 0.800 — 1.97× lift over random |
| Brier | 0.2023 |
| Latency | 46 ms/doc, CPU, no GPU needed |
| Served checkpoint | `deberta_sif/stilt_reset_hlr20/seed2`, selected on **validation** |

TF-IDF on the same split reaches PR-AUC 0.6533, and that gap is *not*
statistically resolvable on 123 rows. Read `docs/RESULTS.md` before quoting any
of this — section 5c is a paired bootstrap showing which differences are real
(none of the in-domain ones) and section 5d shows the one that is.

`python -m ml.selftest` runs 16 end-to-end checks against the served model.
`pytest` runs 139 more. CI runs all of it, plus a real Docker build, on every push.

---

## Provenance

Everything here is either written for this project or downloaded from a public
source under a permissive licence. Nothing is copied from another team's repo.

| source | licence | rows | role |
|---|---|---|---|
| IHM Stefanini industrial safety DB (Kaggle) | CC0 / public domain | 411 | **the labelled set** |
| PHMSA hazmat incident reports, Form 5800.1 | US DOT, public domain | 395,481 | severity labels (stage 2b) + MLM |
| NIOSH injury narrative coding (HuggingFace) | Apache 2.0 | 189,633 | unlabelled, MLM |
| OSHA HSE construction abstracts (Kaggle) | public | 4,827 | unlabelled, MLM |
| OIICS 2.01 code list (CDC/BLS) | US government, public domain | — | reference |

The IOGP Life-Saving Rules are a published industry standard; if you add a rule
classifier later, transcribe them from IOGP Report 459 rather than lifting
anyone's CSV.

---

## The honest starting position

**411 labelled rows.** That is the entire supervised SIF dataset.

No public dataset publishes SIF-potential labels directly, and OISD's Indian
incident portal is restricted to operators, so more cannot simply be downloaded.
The IHM Stefanini set is usable because it carries **Potential Accident Level** —
the severity an incident could have reached, assessed by the safety
professionals who filed it. That is the SIF concept, already labelled by humans.
`data/build_seed.py` maps levels IV and above to `Yes`.

Two limitations, stated up front:

1. **These are Brazilian mining and metals incidents, not oil and gas.** The
   transfer assumption is that SIF mechanisms and barrier failures are shared
   across heavy industry. We think that is defensible, but it is an assumption.
2. **411 rows is too few for a confident binary classifier**, and we do not claim
   one. The product is a **ranker**: an HSE reviewer can read roughly 20 reports
   a shift, so what matters is how good the top of that queue is, not accuracy
   across everything.

### What we did about the 411

Rather than accept the ceiling, the project buys signal from data that is public
and real:

* **590K unlabelled narratives** for masked-language-model domain adaptation.
  Teaches vocabulary — LOTO, permit to work, banksman, gas testing.
* **73K PHMSA serious-incident determinations** for supervised intermediate
  training. Teaches the *task*: a filer's regulatory judgement under 49 CFR
  171.16 that an incident was serious. MLM never shows the model a severity
  decision; this does.

Neither invents a label. In-domain, the second bought nothing we can prove
(+0.0245 PR-AUC, 95% CI [−0.070, +0.122]). Out of domain it changed the model
completely — every STILT seed separates severe from trivial oil-and-gas
narratives, while every MLM-only seed ranks a string of repeated letters above
every real narrative. Since the labels are mining and the target is oil and gas,
that is the axis that matters. `docs/RESULTS.md` §5d.

On a harder probe set — near misses where nobody was hurt, real injuries with low
potential, an Indian wellsite narrative — the served model reaches **ROC-AUC
0.926 and precision@5 of 1.00**, but its threshold misses a potential double
fatality while flagging a printer running out of toner. **The ranking transfers;
the absolute threshold does not.** Use `top_frac` on `/score/batch` for
out-of-domain batches. §5f has the failures in full.

### It was broken, and that is part of the story

An earlier version measured PR-AUC 0.70 and was still useless in deployment: it
flagged **zero of six** realistic oil-and-gas severe narratives and scored
gibberish above an H2S fatality scenario. Nine defects, none of which moved a
ranking metric — a dead ONNX export at ROC-AUC 0.5000 that exited 0, a classifier
head still at initialisation, two of four API bands arithmetically unreachable, a
threshold matched to a checkpoint by filename sort, and a missing model
crash-looping the service instead of degrading (that last one found by CI, in the
one configuration this machine never had).

`docs/RESULTS.md` §2 catalogues them. `ml/selftest.py` is a regression test for
each. That is why the selftest exists and why the export is gated.

---

## Setup

Serving needs none of this — see the three lines at the top. This is for
retraining.

```bash
pip install -r requirements.txt
```

Download the labelled set (needs a Kaggle API key from kaggle.com/settings):

```bash
kaggle datasets download -d ihmstefanini/industrial-safety-and-health-analytics-database
unzip -o industrial-safety-and-health-analytics-database.zip -d data/raw/
```

The unlabelled corpora and the PHMSA monthly files are already in `data/raw/`.

```bash
python ml/preflight.py
```

Checks packages, GPU, VRAM, data and checkpoint portability, then prints the run
order with batch sizes matched to your card. **Follow what it prints.**

---

## Running the service

You do not need a GPU, the training data, or the pipeline. The trained model is
published as a GitHub Release because a single ONNX file is 568 MB, well past
GitHub's 100 MB per-file limit.

```bash
pip install -r requirements-serve.txt
python -m ml.fetch_model       # 531 MB, checksum-verified
python -m ml.selftest          # 16 checks, end to end
uvicorn api.main:app --port 8000
```

Or containerised:

```bash
docker compose up --build      # ~5 min first time; the model is baked in
curl localhost:8000/health
```

`ml/fetch_model.py` pulls the exact artifact `ml/export_onnx.py` promoted after
its fidelity gate passed. Verified from a clean clone: all 16 selftest checks
pass with nothing but the repo and that download. It tries `gh`, then `curl`,
then urllib — TLS interception is common enough that one transport is a
liability.

The image excludes PyTorch: inference is onnxruntime, and transformers is there
for the tokenizer alone. That takes ~800 MB off the image, and the Dockerfile
asserts the assumption at build time rather than at first request. It builds to
1.91 GB with the model inside; CI builds it, starts it and scores a narrative
through it on every push.

### Operations

| | |
|---|---|
| Auth | API key, **off unless `SIF_API_KEYS` is set** — and `/health` says so |
| Rate limiting | token bucket, 60/min per caller, 429 + `Retry-After` |
| Audit trail | one JSON line per prediction: score, threshold, band, and a content hash of the weights |
| Traceability | every response carries `model` and `model_fingerprint` |
| Request tracing | `X-Request-ID`, generated or honoured from upstream |

Narrative text is **hashed, not stored**, in the audit log by default — incident
reports name people and sites. `SIF_AUDIT_TEXT=1` opts in.

Full configuration table and deployment caveats are in `api/README.md`.

**On thresholds:** an absolute threshold assumes incoming reports resemble the
validation split. For out-of-domain batches use `top_frac` on `/score/batch`,
which flags the top slice by rank and is immune to a shift in scale.

---

## Site-level risk

The model reads one narrative at a time, which is the right unit for triage and
the wrong unit for prevention. A serious incident is rarely preceded by one
alarming report; it is preceded by several dull ones that a per-report ranker
correctly scores as unremarkable and a reviewer correctly closes.

`ml/clustering.py` scores the accumulation instead.

```bash
python -m ml.clustering --demo          # worked example, no model, no store
python -m ml.clustering --demo --score  # same narratives, scored by the real model
python -m ml.clustering --site rig-7    # against the real store
```

```
duliajan-rig-7: site risk 0.74 (HIGH) from 5 report(s) in the last 90 days, in 3 hazard group(s).
COMPOUNDING: no single report reached the 0.50 review threshold -- the highest was
0.45 -- but 3 hazard groups are live at once, which together clear it. Per-report
triage would not have surfaced this site.

  0.43  Working at Height  --  2 report(s), latest 4d ago
        strongest 0.38 after decay; recurrence (x1.7 effective) added +0.05
  0.34  Work Authorisation  --  1 report(s), latest 2d ago
  0.32  Hot Work  --  2 report(s), latest 11d ago
```

Four steps, each reconstructible by hand from the reports that produced it:

| step | what it does | why |
|---|---|---|
| decay | `0.5 ** (age/half_life)`, 30-day half-life | unsafe conditions get fixed; old reports are weaker evidence a hazard is live |
| cluster | single-link over IOGP rule overlap + lexical overlap | group reports that describe the same hazard |
| recurrence | `log2`-shaped bonus within a cluster | five reports of one loose plank are one hazard plus evidence nobody is fixing it — not five hazards |
| convergence | noisy-OR across clusters | distinct hazards are distinct paths to harm, so three dull 0.35s give 0.725 |

That last line is the whole point: the combination clears a threshold none of its
parts do, and `compounding` marks exactly that case.

`ml/store.py` is what makes it possible — an append-only SQLite history of scored
reports keyed by site and time, because you cannot correlate reports you threw
away. Ingest is idempotent. It holds narrative text by design (lexical similarity
needs it), which is a deliberate departure from `api/audit.py`, which hashes;
`SIF_STORE_TEXT=0` keeps only hashes and rule ids and clustering degrades to
rule-overlap alone. The database is gitignored and should be treated as holding
the same class of data as the incident system it mirrors.

### Through the API

Pass a `site_id` on `/score` and the score is recorded against that site;
`/sites` then ranks places instead of reports.

```bash
curl -X POST localhost:8000/score -H 'Content-Type: application/json' \
  -d '{"narrative":"A scaffold plank moved underfoot at 8 metres.","site_id":"duliajan-rig-7"}'

curl 'localhost:8000/sites?alerting_only=true'   # sites where compounding is set
curl  localhost:8000/sites/duliajan-rig-7        # clusters, evidence, explanation
```

Or open **`localhost:8000/dashboard`** — the shift queue on the left, the hazard
groups and the reports behind them on the right, and a panel to score a fresh
narrative. One self-contained HTML file served by this process: no build step,
no CDN, works offline and in the container.

Every `/score` response also gains `rules` — the IOGP Life-Saving Rules the
wording touches, the phrases that triggered each, and the commitments a reviewer
should check, straight from `ml/rules.py`. Deterministic matches, so `confidence`
is wording similarity and never a risk level.

Omit `site_id` and nothing is stored: the old `/score` contract is unchanged. A
store that is missing or unwritable returns `recorded: false` with a valid score
and says why on `/health` — recording is a side effect of scoring, never a
precondition for it. Details and the full config table are in `api/README.md`.

**None of this layer is validated, and it must not be quoted as if it were.**
The per-report scores it combines have a PR-AUC on a frozen test set; this has
nothing, because no public dataset publishes site outcomes against near-miss
logs. So it is built to be argued with instead: every constant lives in
`RiskParams` and is echoed in every result, every alert carries the reports and
phrases that caused it, and the combination rule is a standard one with its
assumption stated — noisy-OR treats hazards as independent, and hazards sharing a
crew and a supervisor are not, so it overstates. It also inherits the per-report
model's out-of-domain failures and amplifies them: `--demo --score` scores the
toner-cartridge report at 0.28 and two like it lift an office to WATCH. Read the
evidence, not the number.

---

## Pipeline

Only needed to retrain. Reproduces every number in `docs/RESULTS.md`.

```bash
# 1. Labelled set and frozen splits. Seconds.
python data/build_seed.py
python ml/build_splits.py --write

# 2. Cheap controls first, including the PHMSA controls. Seconds, CPU.
python -m ml.baseline_tfidf

# 3. CONTROL: fine-tune with no adaptation. ~5 min. DO THIS FIRST.
python -m ml.train_deberta --model microsoft/deberta-v3-small --run-name control --seeds 3

# 4. Stage 2 — MLM domain adaptation. Overnight.
python ml/build_mlm_corpus.py
python -m ml.domain_adapt_mlm --model microsoft/deberta-v3-small --steps 15000

# 5. Stage 2b — supervised intermediate task on PHMSA. ~45 min.
python data/build_phmsa.py
python -m ml.train_stilt --init-from model_artifacts/deberta-v3-small_adapted_15k

# 6. Stage 3 — fine-tune each encoder on the 231 SIF rows. ~5 min each.
python -m ml.train_deberta --init-from model_artifacts/deberta-v3-small_adapted_15k --seeds 3
python -m ml.train_deberta --init-from model_artifacts/deberta_phmsa_stilt \
    --reset-head --head-lr-mult 20 --run-name stilt_reset_hlr20 --seeds 3

# 7. Export the winner. Gated on fidelity; refuses to promote a broken export.
python -m ml.export_onnx --checkpoint model_artifacts/deberta_sif/stilt_reset_hlr20/seed2 --promote

# 8. Prove the deployed system actually works.
python -m ml.selftest
```

**Step 6 minus step 3 is the experiment.** Report all of them, not just the best
one.

Run step 3 before committing a night to step 4 — if a plain fine-tune is broken,
MLM will not rescue it, and you will have burned the night finding out.

The last line of step 6 is the promoted recipe: the PHMSA encoder with its task
head discarded and retrained at 20× the encoder learning rate. `--reset-head`
matters because a STILT checkpoint arrives fitted to PHMSA's 20% base rate, not
ours; keeping that head scores worse (`docs/RESULTS.md` §8).

CUDA OOM: halve `--batch-size`, double `--grad-accum`. Effective batch is
unchanged.

---

## The four training stages

Pretrained weights are always the starting point. Nothing trains from scratch.

| stage | who | data | labels | time |
|---|---|---|---|---|
| 1. Pretraining | Microsoft, already done | billions of words | none | download |
| 2. Domain adaptation | you | 590K narratives | **none needed** | overnight |
| 2b. Intermediate task | you | 73K PHMSA rows | severity Yes/No | ~45 min |
| 3. Fine-tuning | you | 231 rows | SIF Yes/No | ~5 min |

One set of weights, adjusted four times. `--init-from` is what chains each stage
onto the previous one's output instead of Microsoft's.

Stage 2 is masked language modelling: random words are hidden and the model
recovers them from context, so the text is its own answer key. DeBERTa was
pretrained on web text and has barely encountered LOTO, permit to work, banksman,
gas testing or line of fire. Stage 2 fixes that before a single label is spent.

Stage 2b is what stage 2 cannot do. Recovering a masked token never shows the
model a severity judgement, so MLM improves the representation and leaves the
decision boundary to 231 rows. PHMSA's `Serious Incident Ind` is a real severity
judgement over free text at the same register as ours (336 chars against our
363) — which is the variable that broke NIOSH transfer. As an intermediate task
it reaches PR-AUC 0.9161 / ROC-AUC 0.9731 on its own held-out split.

Note on DeBERTa-v3 specifically: it was pretrained with replaced-token detection,
not MLM, so the masked-LM head starts from scratch in stage 2. This works, but
watch the loss over the first ~2,000 steps. If it is not falling steadily, switch
to `--model roberta-base`, whose original objective was MLM.

---

## What is in this repo, and what is not

**Committed:** all code, the frozen splits, the labelled seed set, every measured
report, and 61 KB of per-seed raw scores.

**Not committed:** weights and bulk data — `model_artifacts/` (4.0 GB),
`data/raw/` (942 MB), `data/mlm_corpus.txt` (154 MB),
`data/seed/phmsa_serious.csv` (37 MB). All regenerable by the pipeline above; the
serving model comes from the Release.

`data/reports/run_scores/` is worth knowing about. The stage-3 ablations cost
14.6 GB of checkpoints, and the weights were the disposable half — regenerable in
five minutes each because the encoders are kept. What was not disposable is what
each run scored, so the raw validation and test scores, the fitted calibrators
and the run metadata are preserved instead. The paired bootstrap in
`docs/RESULTS.md` §5c re-derives **exactly** from those 61 KB, on a CPU, in
seconds.

---

## Files

| file | what |
|---|---|
| `data/build_seed.py` | Kaggle CC0 source → labelled seed set |
| `data/build_phmsa.py` | PHMSA 5800.1 → 73K severity-labelled rows (stage 2b) |
| `ml/build_splits.py` | group-aware stratified splits, leakage-checked |
| `ml/build_mlm_corpus.py` | raw CSVs → one text file, held-out rows excluded by hash |
| `ml/domain_adapt_mlm.py` | stage 2, continued MLM pretraining |
| `ml/train_stilt.py` | stage 2b, supervised intermediate training |
| `ml/train_deberta.py` | stage 3, end-to-end fine-tuning + calibration |
| `ml/calibration.py` | monotonic score → probability map, fitted on validation |
| `ml/evaluation.py` | the one metrics harness — precision@k, lift, PR-AUC, Brier |
| `ml/export_onnx.py` | ONNX export + int8, **gated** on fidelity and rank agreement |
| `ml/verify_onnx.py` | the same gate, applied to an export from elsewhere |
| `ml/artifacts.py` | run provenance, band margins, the serving pointer |
| `ml/repair_checkpoints.py` | make checkpoints loadable across transformers versions |
| `ml/predict.py` | score narratives from the promoted checkpoint |
| `ml/rules.py` | narrative → IOGP Life-Saving Rule, with the phrases that matched |
| `ml/store.py` | durable history of scored reports, keyed by site and time |
| `ml/clustering.py` | site-level risk: hazard clusters, recurrence, compounding alerts |
| `ml/fetch_model.py` | download the trained model from the GitHub Release |
| `ml/selftest.py` | 16 end-to-end checks, one per defect that once shipped |
| `ml/preflight.py` | environment check + runbook |
| `api/` | FastAPI service — scoring, site risk, dashboard, auth, audit trail |
| `api/static/dashboard.html` | the safety officer’s workspace — one file, no build step |
| `tests/` | 139 tests: HTTP contract, security, calibration, audit, clustering, site API, dashboard |
| `Dockerfile`, `docker-compose.yml` | containerised serving, model baked in |
| `.github/workflows/ci.yml` | tests, selftest, and a real Docker build on every push |
| `docs/RESULTS.md` | every measured number, including the negative ones |

---

## Rules

- **The test set is frozen** once written. `build_splits.py` refuses to overwrite
  it. Re-drawing it mid-project makes every previous number incomparable.
- **Thresholds and calibration are fitted on validation, never on test.** The
  promoted seed is chosen on validation too, and it is not the best seed on test.
  That gap is the cost of not cheating.
- **One evaluation harness** for every candidate. Import `ml/evaluation.py`.
- **One band definition.** `api/` imports it from `ml/predict.py`. When it was
  defined in both places the margins drifted apart and two of the API's four
  bands became unreachable.
- **Report seed variance.** The test set is 123 rows, so single-seed numbers swing
  several points. `train_deberta.py` defaults to 3 seeds and prints mean ± std.
  Never report one seed.
- **Bootstrap before claiming a win.** On 123 rows nothing below roughly 0.10
  PR-AUC is resolvable. Most of the results table is inside that.
- **Held-out narratives are excluded from every auxiliary corpus by SHA-1** before
  training, so the model cannot memorise what it is later scored on.
- **Never ship an export you have not verified.** A DeBERTa ONNX export can fail
  silently and return a constant at ROC-AUC 0.5000 while loading and running
  normally. `export_onnx.py` exits non-zero rather than promote one, and rejects
  an int8 build whose ranking has drifted even when its PR-AUC looks better.
- **Library code does not exit the interpreter.** `SystemExit` inherits from
  `BaseException`, so it slips past `except Exception` — a missing model used to
  crash-loop the container instead of degrading to a `/health` that explains it.
- **Record negative results.** An experiment that failed is information you
  already paid for.

---

## Limitations

Stated here rather than buried, because they bound every number above.

* **411 labelled rows is the binding constraint.** Neither MLM nor STILT removed
  that ceiling; validation PR-AUC peaks within a few epochs and train loss reaches
  ~0.001 by epoch 7.
* **The test set is 123 rows.** Differences smaller than roughly 0.10 PR-AUC are
  not resolvable, which is a fact about the test set, not the models.
* **The out-of-domain evidence is hand-written probes**, not a benchmark.
  Consistent across 9 seeds, but no substitute for real Oil India narratives.
* **The absolute threshold does not transfer out of domain** — it misses a
  potential double fatality and flags a toner cartridge (`docs/RESULTS.md` §5f).
  Ranking holds; use `top_frac`.
* **Paraphrase moves a score by roughly as much as content does.** Individual
  scores are not stable enough to quote; the ordering is what the product uses.
* **Domain mismatch remains**: mining/metals labels, hazmat-transport intermediate
  task, oil-and-gas deployment target.
* **STILT's validation signal does not track its test performance**, which makes
  model selection inside that family unreliable when retraining.
* **int8 is not shipped** — it failed the rank-agreement gate, so the served
  artifact is 568 MB and 46 ms/doc rather than 172 MB and 30 ms/doc.
* **The site-level layer has no ground truth at all.** `ml/clustering.py` is an
  aggregation policy over validated per-report scores, not a measured model, and
  it amplifies the per-report failures above rather than correcting them. Its
  thresholds are chosen for legibility and its independence assumption
  overstates. Treat its output as a reading queue, never as a probability.
* **Not production-hardened.** CORS is open by default, the rate limiter counts
  per process, and there is no key rotation. See `api/README.md`.

This is a triage aid that ranks reports for human review. It does not replace
human judgement, and it should not be described as one that does.
