# Barrier X — Explainer Video Script (1:30)

Voice-over script timed to `BARRIER-X_explainer_1080p.mp4` (1920×1080, 60 fps, 90 s).
Timestamps are the measured beat boundaries in the rendered video.

**Total VO:** ~200 words · **Pace:** ~145 wpm, calm and confident, with a short breath between beats
**Music:** low, steady pulse (ambient or industrial), ducked about 12 dB under the voice. Rise only on the logo hits.
**Pronunciation:** DeBERTa = *deh-BER-tuh* · SIF = *S-I-F* · HSE = *H-S-E* · IOGP = *I-O-G-P* · Hinglish = *HING-lish*

---

## 0:00 – 0:06 · COLD OPEN

**On screen:** the narrative types out → **"Could this have killed someone?"** → the BARRIERX logo forms.
**VO:**
> A valve left untagged. Pressure escapes. Nobody's hurt…
> *(beat)* but could it have killed someone?

**SFX:** soft typing; low boom on the logo.

---

## 0:06 – 0:11 · THE PROBLEM

**On screen:** the safety pyramid builds; **<20%** counts up; *"Find those first."*
**VO:**
> Fewer than one in five incidents can kill. Barrier X finds those first.

---

## 0:11 – 0:19 · 01 / ARCHITECTURE

**On screen:** 5 service nodes pop in, links draw, traffic dots run, then everything but the gateway falls away.
**VO:**
> Five services, one compose file: a React portal, a Go gateway, ML scoring, an HSE agent, and MongoDB.

---

## 0:19 – 0:33 · 02 / GO GATEWAY

**On screen:** login dot → Google OAuth → signed session. Analyze request lights CORS → Log → Auth → proxied to ML → saved to MongoDB. The ML node gets crossed out → *"fallback guidance — still 200 OK"* → **"Degrades. Never crashes."**
**VO:**
> Every request clears three gates: CORS, logging, and auth.
> Google sign-in is verified server-side, then turned into a signed session.
> Reports are proxied to the model and saved.
> *(beat, as the ML node is crossed out)*
> And if the model goes down? The gateway still answers.

---

## 0:33 – 0:42 · 03 / PRODUCT

**On screen:** app window; CSV drops into SIF Analysis; columns tick; progress bar fills as band dots appear; **Export Scored CSV**; the rows hand over to the agent.
**VO:**
> HSE teams just drop in a CSV. Columns are detected, every row is scored, and the ranked results export in one click.

---

## 0:42 – 0:51 · 04 / INSIDE /score

**On screen:** Hinglish normalise → word tokens fly into DeBERTa → Platt calibration curve → pointer lands on the 4-band meter → rules / audit / site-history chips.
**VO:**
> Inside, Hinglish is normalised, DeBERTa reads the narrative in forty-six milliseconds on a CPU, and calibration maps it to one of four risk bands. Not a yes or no.

---

## 0:51 – 0:57 · 05 / ML API

**On screen:** six endpoints feed the API; ops guards branch out; a request burst hits the limiter and two bounce with **429**.
**VO:**
> The API is built to be operated: keys, rate limits, hashed audit logs.

---

## 0:57 – 1:03 · 06 / TRAINING

**On screen:** bars shrink: billions → 590K → 73K → 231 → ONNX export → Release.
**VO:**
> One model, four stages: from billions of words down to 231 labelled reports.

---

## 1:03 – 1:09 · 07 / SITE RISK

**On screen:** three yellow 0.35 bars merge into one red 0.725 bar that crosses the review line → **COMPOUNDING**.
**VO:**
> Three dull reports at one site compound into real danger, and Barrier X flags it.

---

## 1:09 – 1:16 · 08 / HSE AGENT

**On screen:** question → intent router → tools light up → LLM fallback chain (Gemini → Groq → OpenAI → built-in) → cited answer.
**VO:**
> Ask the agent anything. It routes, retrieves the right reports, and answers with citations.

---

## 1:16 – 1:20 · 09 / CI

**On screen:** four pipeline stages, each getting a green ✓.
**VO:**
> Every push is proven: unit tests, a container check, and a sixteen-point selftest.

---

## 1:20 – 1:25 · 10 / RESULTS

**On screen:** **0.667 PR-AUC · 0.757 ROC-AUC · 0.80 P@10 · 46 ms** count up.
**VO:**
> On held-out reports, eight of the top ten flags are true SIF risks.

---

## 1:25 – 1:30 · OUTRO

**On screen:** report → score → band → site risk → agent, then the **BARRIERX** logo and *SIH 2026 · PS 26165 · Oil India Limited*.
**VO:**
> Report. Score. Band. Site. Agent.
> *(beat)* Barrier X. Find the fatal few, first.

**SFX:** music resolves on the logo; hold silence for the last second.

---

## Recording & edit notes

- Record each beat as its own take. In the editor, align each take to the timestamp above. Start the VO about 0.3 s after the section title appears.
- Lines in *(beat)* need a ~0.5 s pause. Those pauses land on a visual hit (the logo, the crossed-out ML node).
- If the reading feels rushed, re-render a slower cut. Set `HOLD = 1.0` in `explainer.py` and the video becomes about 99 s, which gives every beat more air. Then shift the timestamps proportionally.
- Every number spoken here appears in the repo's measured results (README / `docs/RESULTS.md`). Don't add new figures in the VO.
