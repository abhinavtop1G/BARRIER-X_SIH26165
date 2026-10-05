# BARRIER X: Project Summary

**Smart India Hackathon 2026 · Problem Statement SIH26165 (Oil India Limited) · Team GIT PUSH AND PRAY**

## The problem

Oil India's HSE teams receive thousands of unsafe-act, unsafe-condition and near-miss reports. Each one is read by hand, and a reviewer can only read a limited number carefully in a shift.

Fewer than one in five incidents has the potential to cause a **Serious Injury or Fatality (SIF)**, and those incidents mostly come from different causes than minor ones. Cutting minor incidents does not cut fatalities. The warning signs are often already written down in the reports. The hard part is finding them in time.

## What BARRIER X does

BARRIER X reads each free-text report and estimates its **SIF potential**: could this have caused a serious injury or fatality, whatever actually happened? It then **ranks** the reports so reviewers read the most dangerous ones first.

It is deliberately a ranker, not a yes/no classifier. The only public data with SIF-potential labels has 411 rows, which is too little for a confident classifier. What matters to a reviewer is how good the top of the queue is.

For each report it returns:

- a calibrated **SIF probability**
- one of four **risk bands**: HIGH, ELEVATED, BORDERLINE or LOW
- the **IOGP Life-Saving Rules** the wording touches, with the phrases that triggered each match
- short guidance for the reviewer

On top of single reports, it scores **sites**, and it includes an **HSE agent** that answers questions about the reports.

## Architecture

Five services, started together with `docker compose up --build`:

| Service | Stack | Role |
|---|---|---|
| Frontend (:5173) | React, Vite, TypeScript | Sign-in, overview, reports, CSV batch scoring with export, agent chat |
| Gateway (:9000) | Go | CORS, logging and auth on every request; Google sign-in verified server-side, then a signed session; proxies to the ML and agent services; saves reports; returns fallback guidance if the ML service is down |
| ML scoring (:8000) | FastAPI, ONNX Runtime | Scoring, batch scoring, site risk, a built-in dashboard, audit logging |
| HSE agent (:8001) | FastAPI | Routes questions to retrieval tools, then asks an LLM to answer with cited report IDs |
| MongoDB | mongo:6.0 | Users and scored reports |

A demo login, enabled by `DEMO_MODE`, lets evaluators use the app without a Google account.

## The model

The model is **DeBERTa-v3-small**, trained in four stages. Each stage starts from the weights the previous one produced:

1. **Pretraining** (Microsoft): general language.
2. **Domain adaptation:** masked language modelling on 589,717 unlabelled safety narratives from NIOSH, OSHA and PHMSA, so it learns industrial safety vocabulary.
3. **Intermediate task (STILT):** supervised training on 72,990 PHMSA hazmat incident reports labelled with a regulatory "serious incident" determination, so it learns what a severity judgement looks like.
4. **Fine-tuning:** 231 labelled rows from the IHM Stefanini industrial safety dataset (Potential Accident Level IV and above counts as SIF potential), with a fresh classification head trained at 20× the learning rate.

Scores are calibrated with **Platt scaling** fitted on the validation split. Risk band edges come from the calibrated validation scores rather than fixed values.

The model is exported to **ONNX fp32**, which matches the original model's scores to within 0.000008, and runs on a CPU at **46 ms per report** without PyTorch. A compressed int8 version was rejected because it changed the ranking order too much (rank correlation 0.77 against a required 0.95).

Before scoring, reports are normalised: abbreviations are expanded, Hinglish and romanised Hindi or Assamese terms are mapped to English, Devanagari and Assamese script are transliterated, and typos are corrected against a domain lexicon.

## Results

Measured on a frozen test set of 123 held-out reports, base rate 0.407. The model was selected on validation data, never on test.

| Metric | Value |
|---|---|
| ROC-AUC | 0.757 |
| PR-AUC | 0.667 |
| Precision at 10 | 0.80 (1.97× better than random order) |
| Precision / recall at threshold | 0.54 / 0.86 |
| CPU latency | 46 ms per report |

Two findings shape how the product works:

- **Ranking transfers better than the threshold.** On a harder set of 15 hand-written probes, including near misses and an Indian oilfield narrative, ranking reached ROC-AUC 0.926 and all of the top five were genuine high-potential events. The fixed threshold, fitted on mining data, missed some severe narratives. Batch scoring therefore supports `top_frac`, which flags the most dangerous share of any batch.
- **The PHMSA stage mainly helps out of domain.** In-domain, its improvement is not statistically distinguishable from zero on 123 rows. On oil and gas probes, every model trained with it separated severe from trivial narratives, while every model trained without it ranked a meaningless control string above all of them.

Full results, ablations and negative results are in [`RESULTS.md`](RESULTS.md).

## Site-level risk

Serious incidents are often preceded by several unremarkable reports at the same site. BARRIER X records scored reports per site and assesses each site in four steps:

1. **Decay:** each report's weight halves every 30 days.
2. **Clustering:** reports describing the same hazard are grouped by shared Life-Saving Rules and wording.
3. **Recurrence:** repeated reports of the same hazard add weight on a logarithmic curve.
4. **Combination:** hazard groups are combined with noisy-OR.

Three hazard groups at 0.35 each combine to 0.725, so a site can cross the review line even when no single report does. These sites are flagged as **COMPOUNDING**. This layer has no labelled test data behind it, so every alert shows the reports and phrases that caused it.

## HSE agent

The agent routes each question to one or more tools: search the safety reports, assess an asset, summarise risk, or read uploaded reports. It retrieves the relevant records, then asks an LLM to answer and cite report IDs and IOGP rules. It falls back from Gemini 2.5 Flash to Groq Llama 3.3 70B, then OpenAI, then a built-in knowledge base. The LLM explains results; it never decides the ranking.

## Reliability and operations

- One audit line per prediction, with the score, threshold, band and a fingerprint of the exact model weights. Report text is hashed rather than stored by default.
- API keys, a per-caller rate limit, and request IDs.
- The gateway reports the ML service's health and keeps serving when it is down.
- CI runs on every push: unit tests on Python 3.11 and 3.12, integration tests with the real model (including a 16-check selftest), and Docker builds of every service with smoke tests.

## Limitations

- All labels come from Brazilian mining and metals incidents. The system has not yet been tested on real Oil India reports.
- The test set has 123 rows, so small differences between models cannot be resolved.
- The absolute threshold does not transfer well out of domain. Ranking is the reliable signal.
- Site-level risk is not validated against real outcomes.
- The agent is instructed to cite sources, but citations are not yet checked automatically.

## Next steps

- A pilot on real, anonymised Oil India reports to measure transfer and refit the threshold
- Retraining from reviewer decisions
- Automatic citation checking for the agent
- Better Assamese coverage, built with field staff
- A trained IOGP Life-Saving Rules classifier
- Validating site risk against historical outcomes
- Offline field reporting and fully local deployment

## Running it

```bash
docker compose up --build
```

Then open http://localhost:5173 and choose **Continue as demo judge**. The trained model and a 90-second explainer video are on the [Releases](https://github.com/abhinavtop1G/BARRIER-X_SIH26165/releases) page. Setup without Docker is in [`SETUP.md`](../SETUP.md). The story of how the project was built is in [`article.md`](article.md).
