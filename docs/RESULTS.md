# RESULTS — SIF-potential classification

SIH 2026, PS 26165 (Oil India Limited, HSSE safety intelligence).

All numbers measured on `data/splits/test.csv`, 123 held-out real narratives,
frozen before any model was trained and never re-drawn. Every transformer figure
is the mean of 3 seeds with standard deviation, because a 123-row test set moves
several points on seed alone and a single-seed number would be misleading.

To just run the trained model, none of the below is needed — `pip install -r
requirements-serve.txt && python -m ml.fetch_model && python -m ml.selftest`
downloads the promoted checkpoint and re-measures it in about two minutes.

The comparisons in §5 are also re-derivable without a GPU, and without the
weights, from the 61 KB of per-seed scores committed in
`data/reports/run_scores/`.

Reproduce the whole thing from raw data:

```bash
python data/build_seed.py
python ml/build_splits.py --write
python ml/build_mlm_corpus.py
python data/build_phmsa.py
python -m ml.baseline_tfidf
python -m ml.train_deberta --model microsoft/deberta-v3-small --run-name control --seeds 3
python -m ml.domain_adapt_mlm --model microsoft/deberta-v3-small --steps 15000
python -m ml.train_stilt --init-from model_artifacts/deberta-v3-small_adapted_15k
python -m ml.train_deberta --init-from model_artifacts/deberta-v3-small_adapted_15k --seeds 3
python -m ml.train_deberta --init-from model_artifacts/deberta_phmsa_stilt \
    --reset-head --head-lr-mult 20 --run-name stilt_reset_hlr20 --seeds 3
python -m ml.export_onnx --checkpoint model_artifacts/deberta_sif/stilt_reset_hlr20/seed2 --promote
python -m ml.selftest
```

---

## 1. Headline

**The model was never the problem.** A ranker measuring PR-AUC 0.70 on the frozen
test set was shipping behind a serving stack that flagged **zero of six** realistic
oil-and-gas severe narratives, scored a string of repeated letters above an H2S
fatality scenario, and could only ever return two of its four risk bands.

Six independent defects caused that, none of which moved a ranking metric. Three
more surfaced while fixing them — one of which only a test suite could have
found, because it appeared solely in the configuration the development machine
never had. All nine are catalogued in §2, all are fixed, and `ml/selftest.py` is
a regression test for each.

With serving fixed, **supervised intermediate training on 395,481 PHMSA hazmat
incident reports — zero new annotations — leaves in-domain PR-AUC statistically
unchanged but transforms out-of-domain behaviour**: severe-vs-trivial separation
on held-out oil-and-gas probes goes from ROC-AUC 0.83–0.97 to **1.000 on every
seed**, and the margin between severe and trivial narratives widens roughly 5×.
Since the deployment target is oil and gas and the labels are Brazilian mining,
that is the axis that matters.

---

## 2. What was broken

Every one of these passed the existing checks. The model loaded, ran at normal
speed, and returned plausible-looking numbers.

| # | defect | how it presented | evidence |
|---|---|---|---|
| 1 | Classifier head still at initialisation | every probability in [0.494, 0.581] | weight norm 0.753 vs init norm 0.784; decision margin spanned 0.349 logits where a trained head spans ≈[−6,+6]; 100% of test rows had \|margin\| < 0.5 |
| 2 | No calibration | absolute thresholds meaningless | selecting on PR-AUC is scale-invariant, so nothing pressured probabilities to mean anything |
| 3 | ONNX export silently dead | constant output, exit code 0 | `torch.onnx.export` on DeBERTa-v3: PR-AUC 0.4285 / **ROC-AUC 0.5000**, every score 0.533 |
| 4 | 5 of 6 checkpoints unloadable | 3-seed ensemble could load one seed | written by transformers 5.16.1, served on 4.57.6; `extra_special_tokens` list vs dict |
| 5 | Two of four API bands unreachable | everything `ELEVATED` or `BORDERLINE` | band margin ±0.15 against a 0.06-wide score range; `HIGH` needed ≥0.667 when max score was 0.556 |
| 6 | Threshold matched by filename sort | silent model/threshold mismatch | `sorted(glob("deberta_*.json"), reverse=True)`; correct only because `_adapted_15k` happened to sort last |

Consequence, measured before the fixes, on narratives from the actual deployment
domain:

```
severe (6 oil & gas)   mean 0.507   flagged 0 of 6 at the shipped threshold
trivial (6 office)     mean 0.500
control "aaaa bbbb..." 0.521        <- outscored every real severe narrative
```

Three further defects were found and fixed during this work rather than before
it, and it is worth saying how each was caught.

**7. The Platt fitter diverged** on a near-separable validation set — validation
log-loss 5.57 against identity's 1.47, so the `auto` selector silently fell back
to no calibration and shipped a model with ECE 0.40. Caught by reading the
per-seed calibration provenance rather than the headline metric. Now damped with
a backtracking line search (§6).

**8. The export gate was one-sided.** "Did PR-AUC drop?" waved through an int8
model whose **rank correlation with fp32 was 0.77** while its PR-AUC came out
*higher* — luck on 123 rows, not fidelity. The gate now requires Spearman ≥ 0.95
and deletes the artifact when it fails (§7).

**9. A missing model crash-looped the service instead of degrading.**
`resolve_checkpoint` raised `SystemExit`, which inherits from `BaseException` and
therefore slips past the API's `except Exception`. The startup handler is written
precisely so that a missing model produces a `/health` explaining the problem
rather than a container restarting forever with the reason buried in logs — and
it silently could not do that. **Found by CI**, on the first run of the new test
suite, in the one configuration never present on the development machine: no
model on disk. Library code now raises `ModelUnavailable`; the CLI converts it
back to a clean exit at the edge.

That last one is the argument for the test suite in miniature. It was invisible
locally, cost nothing to fix, and would have presented in production as an
unexplained crash-loop.

---

## 3. The constraint

411 labelled rows. That is every SIF-potential label available publicly.

Labels are derived from the IHM Stefanini dataset's **Potential Accident Level** —
the severity an incident could have reached, assessed by the safety professionals
who filed the report. Levels IV–VI map to `Yes`, I–III to `No`. A documented
mapping over an existing human judgement, not a heuristic over free text.

| split | rows | Yes | No | base rate | mean chars |
|---|---|---|---|---|---|
| train | 231 | 94 | 137 | 0.407 | 363 |
| validation | 57 | 23 | 34 | 0.404 | 356 |
| test (frozen) | 123 | 50 | 73 | 0.407 | 368 |

Group-aware and stratified; verified zero normalised-narrative overlap across all
three pairs, and all 411 rows accounted for.

**These are Brazilian mining and metals incidents, not oil and gas.** The transfer assumption is that SIF mechanisms and
barrier failures are shared across heavy industry. Defensible, but it is an
assumption — and §5 is the first measurement in this project that actually tests
it.

---

## 4. The data bought instead of annotated

### 4a. Unlabelled, for MLM (stage 2)

589,717 deduplicated narratives, 153.6 MB, from four public sources. **185
held-out narratives were excluded by SHA-1 before writing.** MLM loss fell
1.995 → 1.556 (perplexity 7.36 → 4.74) over 15,000 steps.

### 4b. Labelled, for the intermediate task (stage 2b) — new

PHMSA Form 5800.1 hazmat incident reports carry `Serious Incident Ind`: a filer's
determination under 49 CFR 171.16 that an incident met a serious-incident
criterion (fatality, major injury, evacuation, closure of a major transport
artery, bulk release, radioactive or marine-pollutant contamination). That is a
severity judgement over a free-text narrative — structurally our task, on a
different substrate.

| | |
|---|---|
| monthly files | 655 (1971-01 … 2025-07) |
| usable narratives | 395,481 |
| serious | 14,598 (3.69%) |
| mean chars | 336 (ours: 363) |
| held-out IHM rows found | 0, asserted by SHA-1 guard |
| used for training | 72,990 at 4:1 negative sampling |

**Why this source and not NIOSH.** §8 records that NIOSH's 63,272 free OIICS
labels made a classifier *worse*. The diagnosis was register: 86-character
hospital-triage shorthand against our 363-character field prose. PHMSA averages
336 characters — the same register, which is the variable that broke NIOSH.

Measured before spending GPU time: TF-IDF trained on PHMSA alone and scored on
the frozen IHM test set reaches PR-AUC 0.5753 / ROC-AUC 0.6227 against a 0.407
base rate. Real transferable signal, weaker than in-domain — the profile of a
useful *intermediate* task, not a replacement.

As an intermediate task it is highly learnable: **PHMSA-internal validation
PR-AUC 0.9161, ROC-AUC 0.9731** after 4,332 steps, rising monotonically.

---

## 5. Results

### 5a. Bag-of-words controls

| model | PR-AUC | ROC-AUC | P@10 | P@20 |
|---|---|---|---|---|
| TF-IDF+LR, IHM only (uni+bigram) | **0.6533** | 0.7266 | 0.80 | 0.65 |
| TF-IDF+LR, PHMSA only | 0.5753 | 0.6227 | 0.70 | 0.65 |
| TF-IDF+LR, PHMSA + IHM pooled | 0.6382 | 0.6710 | 0.80 | 0.75 |

**Pooling PHMSA with IHM makes bag-of-words worse** (0.6382 vs 0.6533). This is
the control that keeps §5b honest: whatever the transformer gains from PHMSA, it
is not "more rows help".

### 5b. Transformers, frozen test set, 3 seeds

`v1` is the pre-fix pipeline; `v2` is post-fix. Ranking metrics are directly
comparable between them — calibration is monotonic and cannot move PR-AUC,
ROC-AUC or precision@k. Brier is not comparable across the boundary, because v1's
operating point was not reproducible.

| run | PR-AUC | ROC-AUC | P@10 | P@20 | recall | Brier | ens PR-AUC | ens ROC-AUC |
|---|---|---|---|---|---|---|---|---|
| v1 control | 0.6123 ±0.015 | 0.6784 ±0.031 | 0.77 | 0.70 | 0.77 | 0.251 | 0.6187 | 0.7099 |
| v1 MLM 5k | 0.6759 ±0.016 | 0.7289 ±0.020 | 0.90 | 0.75 | 0.83 | 0.238 | 0.6813 | 0.7310 |
| v1 MLM 15k | 0.6904 ±0.009 | 0.7357 ±0.012 | 0.90 | 0.77 | 0.89 | 0.221 | 0.6895 | 0.7323 |
| v2 control | 0.6291 ±0.019 | 0.7199 ±0.022 | 0.73 | 0.70 | 0.84 | 0.220 | 0.6423 | 0.7378 |
| v2 MLM 15k | 0.6907 ±0.009 | 0.7359 ±0.012 | 0.90 | 0.77 | 0.89 | **0.205** | 0.6950 | 0.7375 |
| v2 STILT, head kept | 0.6940 ±0.043 | 0.7482 ±0.037 | 0.90 | **0.80** | 0.75 | 0.213 | **0.7214** | **0.7603** |
| **v2 STILT, head reset** ★ | 0.6782 ±0.027 | **0.7528 ±0.004** | 0.83 | 0.78 | 0.86 | **0.204** | 0.7032 | 0.7597 |

★ promoted for serving. Base rate 0.407.

**v2 MLM 15k reproduces v1 MLM 15k exactly** (0.6907 ±0.009 vs 0.6904 ±0.009;
seed 0 matches to four decimals at 0.7013 / 0.7378). The pipeline is
deterministic, and the only thing that changed for that configuration is
calibration — which improved Brier 0.221 → 0.205 while leaving ranking untouched,
exactly as a monotonic map must.

### 5c. Is the STILT gain real? No — not on 123 rows

Paired bootstrap, 5,000 resamples of the frozen test set, against v2 MLM 15k:

| comparison | Δ PR-AUC | 95% CI | P(better) | verdict |
|---|---|---|---|---|
| STILT (head kept) − MLM 15k | +0.0245 | [−0.070, +0.122] | 0.70 | **not distinguishable from zero** |
| STILT (head reset) − MLM 15k | +0.0073 | [−0.079, +0.096] | 0.57 | not distinguishable from zero |
| control − MLM 15k | −0.0425 | [−0.141, +0.053] | 0.20 | not distinguishable from zero |

So: **we do not claim a PR-AUC improvement from PHMSA.** The point estimate is
positive and the confidence interval contains zero. On a 123-row test set nothing
smaller than roughly 0.10 PR-AUC is resolvable, which is a fact about the test set
rather than about any of these models.

**This is re-derivable without a GPU or the weights.** The stage-3 checkpoints
were 14.6 GB and have been deleted; what survives is 61 KB of per-seed raw
scores, fitted calibrators and run metadata in `data/reports/run_scores/`, which
is committed. Re-running the bootstrap from those files alone reproduces the
table above exactly — `+0.0245, [−0.0699, +0.1215], P(better) = 0.70` — in
seconds on a CPU. That was verified before the weights were deleted, not
assumed afterwards.

### 5d. Where PHMSA does change the model: out of domain

The deployment target is oil and gas; the labels are Brazilian mining. So the
models were probed with 12 hand-written oil-and-gas narratives — 6 with obvious
SIF potential (suspended load, H2S exposure, live 33kV contact, unpermitted
confined-space entry, scaffold collapse, high-pressure gas ignition) and 6
obviously trivial (coffee spill, flickering bulb, empty toner) — plus one control
string of repeated letters that carries no meaning at all.

Per seed, calibrated, nothing cherry-picked:

| checkpoint | OOD ROC-AUC | severe mean | trivial mean | gap | control | real narratives above control |
|---|---|---|---|---|---|---|
| MLM 15k seed0 | 0.972 | 0.164 | 0.090 | 0.075 | 0.269 | **0 / 12** |
| MLM 15k seed1 | 0.833 | 0.231 | 0.197 | 0.033 | 0.516 | **0 / 12** |
| MLM 15k seed2 | 0.861 | 0.262 | 0.257 | 0.006 | 0.279 | **0 / 12** |
| STILT keep seed0 | **1.000** | 0.457 | 0.245 | 0.212 | 0.300 | 8 / 12 |
| STILT keep seed1 | **1.000** | 0.486 | 0.304 | 0.182 | 0.358 | 7 / 12 |
| STILT keep seed2 | **1.000** | 0.457 | 0.286 | 0.172 | 0.335 | 7 / 12 |
| STILT reset seed0 | **1.000** | 0.513 | 0.252 | 0.261 | 0.321 | 6 / 12 |
| STILT reset seed1 | **1.000** | 0.437 | 0.200 | 0.237 | 0.302 | 6 / 12 |
| STILT reset seed2 ★ | **1.000** | 0.518 | 0.270 | 0.248 | 0.329 | 7 / 12 |

Six out of six STILT seeds separate severe from trivial perfectly. Three out of
three MLM-only seeds rank a meaningless string of repeated letters **above every
real narrative, severe and trivial alike**. The severe-trivial margin is
0.17–0.26 for STILT against 0.006–0.075 for MLM-only — roughly 5× wider.

This is the result worth reporting, and it is *not* visible in any in-domain
metric. It says the MLM-only model had learned surface features of Brazilian
mining prose, and that 73K real severity judgements at a matching register taught
it something transferable instead.

Caveat, stated plainly: **12 hand-written probes are an indicator, not a
benchmark.** The consistency (9 of 9 seeds behaving according to their family) is
what makes it worth acting on. A proper OOD evaluation needs real Oil India
narratives, which we do not have.

**And that probe set was too easy.** Six obviously-catastrophic narratives against
six obviously-trivial ones is a contrast a model can pass without understanding
the task — which is why every STILT seed scores exactly 1.000 above. It was
sufficient to separate the model families, which is what it was used for, but it
is not a measure of whether the model is *good*.

`ml/selftest.py` now carries a harder 15-probe set, described in §5f. The
per-seed comparison above cannot be re-run against it: those stage-3 checkpoints
were deleted after the promotion decision, and only their test-set scores were
preserved. The table stands as a measurement of the easier set, which is what it
always was.

### 5f. The harder probe set, and where the model actually fails

The replacement leads with **near misses**, because that is the product concept:
SIF potential asks "could this have been fatal", not "was anyone hurt". It adds
**real injuries with low potential**, which a naive severity model over-ranks,
and an **Indian oil-and-gas narrative**, since the deployment target is Oil India
and every labelled row is Brazilian mining. Nine high-potential against six low.

The served model on that set:

| | |
|---|---|
| ROC-AUC | **0.926** |
| precision@5 | **1.00** — the top of the queue is all genuine |
| high-potential mean | 0.422 [0.295, 0.519] |
| low-potential mean | 0.280 [0.247, 0.331] |
| at the threshold | 7 of 9 high flagged, 2 of 6 low leaked |

The ranking holds. **The threshold does not.** Two failures worth naming:

```
0.299  a scaffold plank slipped at 8 metres              NOT flagged
0.295  Duliajan workover, travelling block came down
       while two crew were positioned beneath it          NOT flagged
0.331  the printer in the HSE office ran out of toner     flagged
```

A potential double fatality scores below a toner cartridge. Two further
observations from the same probe:

* **It does not read severity keywords.** Appending "A fatality occurred" to a
  budget-meeting note *lowered* the score, 0.350 → 0.324. Not keyword matching —
  but not reading meaning either, on text unlike its training distribution.
* **Paraphrase moves it as much as content does.** The same incident (fall from a
  ladder, unhurt, office) scores 0.407–0.527 depending on wording. That ±0.12
  swing is comparable to the entire 0.142 gap between the two classes.

Which is the argument for rank-based flagging. On the same 15 reports:

| rule | precision | recall |
|---|---|---|
| absolute threshold 0.3027 | 0.78 | 0.78 |
| **top 5 by rank** | **1.00** | 5 of 9 |
| top 10 by rank | 0.80 | 8 of 9 |

`/score/batch` takes `top_frac` for exactly this reason. **On real Oil India
reports, use it rather than the absolute threshold** — the threshold was fitted
on Brazilian mining validation data and §5f is the measurement showing it does
not transfer.

The selftest asserts ranking (ROC-AUC ≥ 0.85) and top-of-queue precision
(≥ 0.80), not flagging. Asserting that every high-potential narrative clears the
threshold would be asserting something known to be false.

### 5e. What the promoted model actually does

`stilt_reset_hlr20/seed2`, selected by **validation** PR-AUC (0.6581), never by
test:

```
n=123  base_rate=0.407  threshold=0.3027 (precision floor >=0.50, on validation)
precision=0.5443  recall=0.8600  F1=0.6667
PR-AUC=0.6667  ROC-AUC=0.7570  Brier=0.2023
TP=43 FP=36 TN=37 FN=7
P@10=0.800 (lift 1.97x)   P@20=0.800 (lift 1.97x)   P@50=0.600
bands: HIGH=68  ELEVATED=11  BORDERLINE=17  LOW=27
```

Note the seed selected on validation is not the best seed on test (0.6667 against
0.7092 for seed1). That gap is the cost of not cheating, and it is the honest
number to quote.

### 5g. Ingestion: does normalising a field report help?

`ml/ingest.py` rewrites an incoming report before the model reads it —
transliterating Devanagari and Assamese, expanding oilfield abbreviations,
mapping romanised Hindi/Assamese vocabulary to English, and repairing typos
against a domain lexicon. Rewriting the input can hurt as easily as help, so it
gets measured rather than assumed.

**The test.** Ten incidents, each written twice: once as the clean English the
model was trained on, once as it would actually arrive from a rig. Score both,
plus the normalised version of the noisy one. If normalisation works, the noisy
twin should score like its clean original.

`python -m ml.ingest --probe`

| | raw | normalised |
|---|---|---|
| mean \|gap\| to the clean twin | 0.0788 | **0.0571** |
| max \|gap\| | 0.1754 | 0.1435 |
| Spearman against the clean ordering | 0.273 | **0.624** |
| pairs closer to clean | — | 7 of 10 |

**The mean gap closed by 0.0218, 95% CI [−0.0185, +0.0604] — not resolvable on
ten pairs.** Same verdict as §5c and for the same reason: the effect may be
real, the sample cannot show it. Quoting the 28% reduction without the interval
would be the mistake this document exists to prevent.

The number that moved further than its noise is the **ranking**: Spearman
against the clean ordering goes 0.273 → 0.624. That matters more than the gap,
because ranking is the product — §5f already established that this model's order
transfers and its absolute threshold does not.

**Where it works and where it does not:**

```
typos        gap 0.047 -> 0.000    exact recovery; the text is restored verbatim
             gap 0.024 -> 0.000
abbrev       gap 0.105 -> 0.003    H2S/SCBA/GCS expanded
hinglish     gap 0.175 -> 0.048    majdoor/machan/gir gaya mapped
assamese     gap 0.141 -> 0.143    NO IMPROVEMENT
mixed        gap 0.022 -> 0.129    WORSE
```

The typo rows are the sanity check: repairing a typo restores the original
string, so the gap must go to zero, and it does. The Assamese row is the honest
failure — `খহি পৰি` ("fell") transliterates correctly to `khahi pari` and then
finds no glossary entry, so only *worker* and *injury* were recovered and the
score barely moved. The fix is a lexicon entry, and **the lexicon was
deliberately not tuned against this probe set**: a glossary edited until its own
test passes measures nothing.

The `mixed` regression is worth stating plainly. That pair's raw score happened
to sit 0.022 from its clean twin by luck; normalisation moved it to a different
wrong place. With three of ten pairs worse, normalisation is not free.

**Standing of this result.** Hand-written probes, not a benchmark — the same
standing as §5f. No public corpus of Assamese or Hinglish oilfield near-miss
reports exists to test against, which is the same wall the labelled data hit in
§3. Ten pairs written by the same person who wrote the lexicon is the weakest
evidence in this document, and it is reported because the alternative is
shipping a rewriting step with no evidence at all.

**What would settle it.** A few hundred real Oil India reports with their
original text preserved, normalised and scored both ways. That is a
half-day's work once the reports exist and cannot be done before.

---

---

## 6. Calibration

`ml/calibration.py`. Platt scaling fitted on the 57-row validation split, never
on test. Two parameters, because anything more flexible fits noise at that size.

Because the map is **monotonic**, PR-AUC, ROC-AUC and precision@k are
mathematically unchanged — verified to six decimal places. What changes is that
the number means something:

| | raw | calibrated |
|---|---|---|
| served score range | [0.000, 1.000] saturated | [0.205, 0.596] |
| Brier (test) | 0.390 (worst seed) | 0.202 |
| ECE (validation, worst seed) | 0.402 | 0.084 |
| bands populated on test | 2 of 4 | **4 of 4** |

Two implementation notes worth carrying forward:

* **The fitter must be damped.** Undamped Newton–Raphson diverged on a
  near-separable validation set — IRLS weights `p(1−p)` underflow at logits near
  ±5.5, the Hessian goes ill-conditioned, and a full step overshoots. It returned
  a validation log-loss of 5.57 against identity's 1.47, so the `auto` selector
  fell back to no calibration and shipped ECE 0.40. With backtracking line search
  the same case fits cleanly (ECE 0.402 → 0.084).
* **Band margins must come from the data.** A fixed ±0.15 against a narrow score
  distribution makes `HIGH` and `LOW` unreachable. `ml.artifacts.band_margin_for`
  derives the margin from the calibrated validation range and stores it in
  `run_meta.json`; for the served model it is 0.0477.

Raw validation and test scores are saved beside every checkpoint, so a calibrator
can be refit without a GPU (`python -m ml.calibration --refit-all`).

---

## 7. Deployment

### 7a. The export gate

Exported with `optimum` and gated against PyTorch on the frozen test set:

| format | size | PR-AUC | ROC-AUC | max abs delta | Spearman vs fp32 | CPU latency | shipped |
|---|---|---|---|---|---|---|---|
| PyTorch fp32 | 554 MB | 0.6737 | 0.7570 | — | 1.0000 | — | — |
| **ONNX fp32** | 568 MB | 0.6737 | 0.7570 | 0.000008 | 1.0000 | 46.2 ms/doc | **yes** |
| ONNX int8 | 172 MB | 0.7351 | 0.7803 | 0.997591 | **0.7688** | 29.8 ms/doc | **rejected** |

The int8 build posts a *higher* PR-AUC and was still rejected. Its rank
correlation with fp32 is 0.77: quantisation reshuffled the queue, and the queue
order is the product. On 123 rows a reshuffle can land favourably — that is luck,
not fidelity, and a one-sided "did PR-AUC drop?" check cannot tell the difference.
The gate now requires Spearman ≥ 0.95 for int8, deletes the artifact when it
fails, and serves fp32 instead.

The fp32 export being **numerically identical** is the load-bearing line.
`ml/export_onnx.py` exits non-zero rather than promote a failing export, and
`ml/verify_onnx.py` applies the same gate to an artifact that arrived from
somewhere else. The earlier `torch.onnx.export` artifacts (ROC-AUC 0.5000) are
rejected by all three checks — constant output, chance ROC-AUC, and fp32 delta —
and have been deleted from the repo.

Serving provenance is explicit: `model_artifacts/SERVING.json` names the promoted
checkpoint, its ONNX directory, its threshold and its calibration. Nothing is
inferred from a filename, and every API response carries `model` and
`calibration` so a stored score can be traced months later.

### 7b. Getting the model

`model_artifacts/` is 4.0 GB and a single ONNX file is 568 MB, past GitHub's
100 MB per-file limit, so the weights are not in the repository. The serving
bundle — ONNX fp32, tokenizer, calibration, run metadata, serving pointer — is a
GitHub Release, 531 MB compressed, fetched by `ml/fetch_model.py` with SHA-256
verification and an extractor that refuses absolute paths, traversal and links.

It tries `gh`, then `curl`, then urllib. That is not belt-and-braces: on the
machine this was built, plain urllib is reset mid-stream by TLS interception
while the other two succeed, and `gh` in turn hit a handshake timeout inside CI
where `curl` worked. Any single transport would have failed somewhere.

**Verified from a clean clone**: `git clone`, `python -m ml.fetch_model`,
`python -m ml.selftest` → 16/16, with the same numbers as the development
machine.

### 7c. Container

`docker compose up --build`. The model is baked in, so the container needs no
network and no volume at run time; `--build-arg FETCH_MODEL=0` skips that for
volume mounting instead.

The image excludes PyTorch — inference is onnxruntime and transformers is present
for the tokenizer alone, which is ~800 MB saved. The Dockerfile asserts that
assumption at build time rather than leaving a container that installs cleanly
and dies on its first request. Final size **1.91 GB**; ~560 MB model, most of the
remainder onnxruntime plus the pandas/scikit-learn stack that lets `ml.selftest`
run inside the container.

Built and run in CI, which then scores a narrative through it. The container
reproduces the development machine exactly: `score=0.3733`, model fingerprint
`e3b1a0f55a1633f9` — same weights, same answer.

### 7d. Serving surface

| | |
|---|---|
| Audit trail | one JSON line per prediction: score, threshold, band, decision, latency, caller, and a content hash of the weights |
| Narrative privacy | text is SHA-256 hashed, not stored, by default |
| Auth | API key, **off unless `SIF_API_KEYS` is set**, and `/health` advertises which |
| Rate limiting | token bucket per caller, 429 with `Retry-After` |
| Tracing | `X-Request-ID`, generated or honoured from upstream |

A safety system has to answer "why was this report not flagged?" months later.
That needs the score, the operating point, and *which model* produced it — a
score with no model identity is not evidence. The fingerprint is a content hash
rather than a checkpoint name because names get reused and file contents do not.

Both auth and rate limiting are in-process. The limiter therefore counts per
process, so N replicas permit N times the configured rate; that is a documented
limitation, not an oversight.

### 7e. How all of this is verified

| | |
|---|---|
| `ml/selftest.py` | 16 end-to-end checks, one per defect in §2 |
| `pytest` | 58 cases: HTTP contract, security, calibration properties, audit trail |
| CI, every push | unit tests on 3.11 and 3.12 · model fetch + selftest + full suite · Docker build, run and score |

46 of the 58 tests need no model. That is deliberate: the weights are a 531 MB
download, and a suite that cannot start without them is a suite that stops
running on every push. The rest carry a marker and skip cleanly.

Several are regression tests for §2 and §6 — that calibration leaves PR-AUC,
ROC-AUC and precision@k unchanged; that Platt converges on near-separable data;
that all four bands stay reachable; that narrative text is not written to the
audit log by default. If the first of those ever fails, every number in this
document quietly stops meaning what it says.

---

## 8. Negative and inconclusive results

Recorded because an experiment that failed is information already paid for.

**PHMSA does not improve in-domain PR-AUC detectably.** §5c. Point estimate
+0.0245, 95% CI [−0.070, +0.122]. Reported as inconclusive, not as a win.

**Pooling PHMSA with IHM hurts bag-of-words.** 0.6382 vs 0.6533. Sequential
transfer helps where naive pooling does not.

**Resetting the STILT head is not free.** With the encoder's learning rate it is
clearly worse (0.6173 ±0.022); it only works with a 20× head learning rate
(0.6782 ±0.027), which is what the promoted model uses.

**Raising the head learning rate is not uniformly good.** It helps the stock
encoder (0.6291 → 0.6382) and *hurts* the MLM-adapted one (0.6907 → 0.6589, with
seed variance quadrupling from 0.009 to 0.038). The undertrained head was a real
defect, but calibration — not a bigger head step — is the fix that generalises.

**OIICS-derived rule labels do not transfer.** NIOSH's 63,272 free rule labels
scored 0.500 alone and 0.542 pooled, against a 0.708 baseline. 11,500 extra
labelled rows made it worse. Register mismatch, as above.

**A plain fine-tuned transformer loses to TF-IDF** on this data (0.6291 vs
0.6533). Reported rather than buried, because it is what makes the adaptation
results meaningful.

---

## 9. Limitations

* **411 labelled rows is the binding constraint.** Validation PR-AUC peaks within
  a few epochs in every seed; train loss reaches ~0.001 by epoch 7. Neither MLM
  nor STILT removed that ceiling.
* **The test set is 123 rows.** The bootstrap in §5c puts the resolvable
  difference at roughly 0.10 PR-AUC. Most of the table's spread is not resolvable.
* **STILT's validation signal does not track its test performance** (val 0.557
  → test 0.732 on one seed; val 0.598 → test 0.647 on another). Model selection
  within the STILT family is therefore unreliable, which is a real operational
  risk when retraining.
* **The OOD evidence is hand-written probes**, not a benchmark — 12 for the
  per-seed comparison in §5d, 15 harder ones in §5f. Consistent across 9 seeds,
  but no substitute for real Oil India narratives.
* **The threshold does not transfer out of domain.** §5f: it misses a potential
  double fatality and flags a toner cartridge. Ranking holds at ROC-AUC 0.926;
  use `top_frac` on real reports.
* **Paraphrase moves the score by roughly as much as content does** (±0.12 on the
  same incident reworded, against a 0.142 between-class gap). Individual scores
  are not stable enough to quote; the ordering is what the product uses.
* **Domain mismatch remains**: mining/metals labels, hazmat-transport intermediate
  task, oil-and-gas deployment target.
* **Severity classes are thin.** Potential Accident Level VI has 1 example and V
  has 28, so the model mostly learns "IV vs III".
* **The 15,000-step adaptation was run in two sessions**; optimizer state and LR
  schedule reset at the boundary.
* **No rule classifier.** Requires transcribing the IOGP Life-Saving Rules from
  Report 459.
* **int8 is not shipped**, so the deployed artifact is 568 MB and 46 ms/doc rather
  than 172 MB and 30 ms/doc. A saturated model quantises badly; a less confident
  one might not.
