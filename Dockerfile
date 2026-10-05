FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    HF_HUB_OFFLINE=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements-serve.txt .
RUN pip install -r requirements-serve.txt

RUN python -c "from transformers import AutoTokenizer; import onnxruntime, fastapi; \
print('tokenizer stack imports OK')"

RUN python -c "import importlib.util; \
print('torch absent, image is slim' if not importlib.util.find_spec('torch') \
else 'note: torch is installed, image is ~800 MB larger than necessary')"

COPY ml/ ./ml/
COPY api/ ./api/
COPY data/splits/ ./data/splits/
COPY data/reference/ ./data/reference/
COPY README.md ./

ARG FETCH_MODEL=1
RUN if [ "$FETCH_MODEL" = "1" ]; then \
        python -m ml.fetch_model && \
        python -c "\
import sys; sys.path.insert(0, '.'); \
from ml.predict import Scorer; \
s = Scorer(); \
p = float(s(['H2S alarm at the wellhead; two technicians without breathing apparatus, one collapsed.'])[0]); \
print(f'build smoke test: backend={s.backend} calibration={s.calibrator.method} score={p:.4f}'); \
sys.exit('scorer returned a degenerate value') if not (0.0 < p < 1.0) else None"; \
    else \
        echo "FETCH_MODEL=0 -- mount model_artifacts at runtime"; \
    fi

RUN useradd --create-home --uid 10001 avertx \
    && mkdir -p /app/data && chown -R avertx:avertx /app
USER avertx

EXPOSE 8000

ENV SIF_WORKERS=1 \
    ALLOWED_ORIGINS=*

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS http://localhost:8000/health | grep -q '"model_ready":true' || exit 1

CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers ${SIF_WORKERS}"]
