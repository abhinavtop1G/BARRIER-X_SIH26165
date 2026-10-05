# Running BARRIER X on a fresh machine

Four services on localhost: a React frontend, a Go gateway, an AI HSE agent, and
the SIF scoring model. `run_all.ps1` starts all four.

---

## What you need first

| | |
|---|---|
| **Python 3.11 or 3.12** | **not 3.13/3.14** — `onnxruntime` publishes no wheels for them, so the scoring service installs and then fails on the first narrative |
| **Node 18+** | frontend |
| **Go** | gateway; `run_all.ps1` calls `go run`, so it must be on PATH |
| **Git** | |

Check all three resolve before starting:

```powershell
py -3.12 -V
node -v
go version
```

If `go version` fails, Go is installed but not on PATH — open a **new** terminal
after installing, since Windows only gives the updated PATH to new processes.

---

## Setup

```powershell
git clone https://github.com/abhinavtop1G/BARRIER-X_SIH26165.git
cd BARRIER-X_SIH26165

# 1. Python environment and serving dependencies
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements-serve.txt

# 2. The trained model. 568 MB, checksum-verified, not in the repo.
.\.venv\Scripts\python -m ml.fetch_model

# 3. Frontend dependencies
cd frontend
npm install
cd ..

# 4. Configuration
copy .env.example .env
copy frontend\.env.example frontend\.env
#    then fill both in - see below

# 5. Start everything
.\run_all.ps1
```

Open **http://localhost:5173** and sign in with Google.

### Not in the repo

`.env`, `.venv/`, `model_artifacts/`, `frontend/node_modules/` and
`frontend/.env` are all gitignored — steps 1 to 4 are what create them. Secrets
and a 568 MB binary do not belong in git.

---

## Configuration

`.env` — the comments in `.env.example` say what each one does. The two people
most often get wrong:

- **`PORT` / `GATEWAY_PORT` must be 9000.** The Vite dev proxy targets 9000. Set
  them to anything else and sign-in fails with a connection error that looks
  like an auth problem.
- **`GEMINI_API_KEY`** — everyone should use their own. Free from
  [aistudio.google.com](https://aistudio.google.com), takes two minutes. Without
  it the agent still answers, but from a canned fallback rather than a model.

`frontend/.env` — **`VITE_GOOGLE_CLIENT_ID` is required**, the same value as
`GOOGLE_CLIENT_ID` in `.env`. There is no demo bypass; with it empty there is no
way to sign in.

The client ID is public by design and safe to share. The Atlas URI and the LLM
keys are not — send those through a password manager, never chat. There is no
`GOOGLE_CLIENT_SECRET`: nothing reads one.

---

## With Docker

All five services (frontend, gateway, ML scoring, HSE agent, MongoDB) run from the
repo root:

```bash
docker compose up --build
```

Compose reads these from a `.env` file next to `docker-compose.yml`:

| variable | used by | notes |
|---|---|---|
| `GOOGLE_CLIENT_ID` | frontend (build time), gateway | needed for Google sign-in; optional while demo mode is on |
| `JWT_SECRET` | gateway | if unset, a random key is generated and sessions reset on restart |
| `DEMO_MODE` | gateway | defaults to `true` in compose: the login page offers **Continue as demo judge**, so no Google account is needed. Set `DEMO_MODE=false` for real deployments |
| `GEMINI_API_KEY` / `GROQ_API_KEY` / `OPENAI_API_KEY` | agent | optional; the agent falls back to built-in HSE answers without them |

The frontend is a static build served by nginx. `VITE_*` values are baked in at
build time, so after changing `GOOGLE_CLIENT_ID`, rebuild with
`docker compose up --build frontend`. The ML image downloads the model while it
builds, so the first build takes about 5 minutes.

---

## The four services

| service | port | started by |
|---|---|---|
| SIF scoring (FastAPI + ONNX) | 8000 | `.venv` python |
| Go API gateway | 9000 | `go run main.go` |
| AI HSE agent (FastAPI + Gemini) | 8001 | `py` |
| React frontend (Vite) | 5173 | `npm run dev` |

The gateway proxies `/score` to 8000 and `/agent/chat` to 8001, and persists
reports to MongoDB.

---

## Checking it actually works

Health first:

```powershell
curl http://localhost:8000/health    # model_ready must be true
curl http://localhost:9000/health
curl http://localhost:8001/health
```

Then the part health checks cannot tell you. **Both the gateway and the agent
degrade into plausible-looking output rather than failing.** A demo can look
entirely healthy while neither the model nor the LLM is being reached.

**Is it really the model?** Score something in SIF Analysis and open the
provenance panel under the result. A real prediction names a checkpoint and a
fingerprint. If it says `keyword estimate — ML service unreachable`, the
scoring service on 8000 is down and the number is a keyword guess.

**Is it really the LLM?** Ask the agent something that fits none of its canned
branches — not "what are the IOGP rules", which has a hardcoded answer. A reply
starting `**HSE Guidance for '...'` or `**Safety Assessment regarding '...'`
is the fallback. The agent window prints the reason.

---

## Troubleshooting

**Agent gives canned answers.** Three causes, all of which look identical in the
UI. The agent window now prints which one:
- no `GEMINI_API_KEY` in `.env`
- the network intercepts TLS — `CERTIFICATE_VERIFY_FAILED: unable to get local
  issuer certificate`. `httpx` trusts certifi's bundle, not the Windows store.
  Export the Windows roots to a PEM and point `BARRIERX_CA_BUNDLE` at it;
  `run_all.ps1` picks it up automatically. The same interception breaks `pip`.
- the model name was retired — Gemini deprecates models, so a 404 here means
  `agent.py` needs a current one from `ListModels`

**Every score says "keyword estimate".** The service on 8000 is not running or
still loading — it reads a 568 MB model at startup. Check `model_ready:true`.
If `ml/fetch_model` was never run, there is no model to load.

**Reports and Overview are empty, or show incidents nobody entered.** The
gateway could not reach MongoDB and fell back to in-memory seeded data. Atlas
enforces an IP allowlist, so a new machine needs adding under Network Access.

**`go` not recognised.** Installed, but this terminal was opened before the
install. Open a new one.

**`onnxruntime` will not install.** Python 3.13/3.14. Build the venv with 3.11
or 3.12.

**Port 5173 in use.** Vite will take 5174 and print it — but `vite.config.ts`
only proxies `/api` from the port it is actually serving, so use the URL it
prints rather than assuming 5173.

---

## Notes for a demo

The scoring model ranks reports; it does not classify them reliably in absolute
terms. On the bundled demo dataset the H2S report lands around rank 15 and the
confined-space entry around 25, while a perimeter-lighting observation reaches
rank 5. That is documented out-of-domain behaviour — `docs/RESULTS.md` §5f — and
the honest framing is that the ranking transfers and the absolute threshold does
not.

The demo dataset is deliberately hazard-rich, so the SIF-potential percentage on
the Overview card runs far above the "under 20% of incidents carry SIF
potential" figure in the pitch. That is a property of the sample, not the model.

Agent replies take roughly 6-11 seconds. A spinner shows throughout.
