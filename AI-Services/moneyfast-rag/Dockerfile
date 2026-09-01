# MoneyFast RAG service. HTTP on 8100.
#
# Multi-stage, matching the other Python services: `test` runs the suite,
# `runtime` ships without pytest or the tests directory.

# ---------------------------------------------------------------------------
# Stage 1: base. Runtime deps, application code, and the embedding model.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
    EMBEDDING_DIMENSION=384 \
    FASTEMBED_CACHE_PATH=/opt/fastembed

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app.py embeddings.py store.py chunking.py ./

# Bakım betikleri. Bu servis sistemdeki tek vector-db kredensiyelini tuttuğu
# için korpusa dokunan her iş buradan çalışmak zorunda -- ve betikler image'a
# girmezse `docker compose exec rag python -m scripts.<ad>` çalışmıyor, ki
# ikisinin de docstring'inde yazan komut buydu.
COPY scripts/ ./scripts/

# Bake the ONNX weights into the image. Without this the first request after a
# cold start would try to reach Hugging Face — and the rag container is not on
# ai-egress, so that request would hang rather than fail fast. Downloading at
# build time also means the runtime image needs no network at all.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')" \
 && chmod -R a+rX /opt/fastembed

# ---------------------------------------------------------------------------
# Stage 2: test.
#   docker build --target test -t moneyfast-rag:test .
# ---------------------------------------------------------------------------
FROM base AS test

RUN apt-get update \
 && apt-get install -y --no-install-recommends make \
 && rm -rf /var/lib/apt/lists/*

COPY requirements-test.txt pytest.ini .coveragerc Makefile ./
RUN pip install --no-cache-dir -r requirements-test.txt

COPY tests/ ./tests/

# Runs as root on purpose: this stage writes coverage artefacts and never ships.
RUN make test

# ---------------------------------------------------------------------------
# Stage 3: runtime. What actually ships.
# ---------------------------------------------------------------------------
FROM base AS runtime

RUN useradd --create-home --uid 10003 raguser \
 && chown -R raguser:raguser /app
USER raguser

EXPOSE 8100

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8100"]
