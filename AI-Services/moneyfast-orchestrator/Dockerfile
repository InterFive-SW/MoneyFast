# MoneyFast orchestrator agent.
# Multi-stage: `test` runs the suite and the 100% coverage gate, `runtime`
# ships without pytest, make, or the tests directory.

# ---------------------------------------------------------------------------
# Stage 1: base. Runtime dependencies and application code.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

# Her modül burada ADIYLA yazılı. Yeni bir dosya eklerken buraya da
# eklenmezse servis import hatasıyla açılmıyor ve testler yeşil kalıyor --
# testler dosya sisteminden değil, kaynak ağacından çalışıyor.
COPY orchestrator.py prompts.py mcp_client.py api.py widgets.py \
     sources.py agent_trace.py sanitize.py ./

# ---------------------------------------------------------------------------
# Stage 2: test. Fails the build on any test failure or a coverage drop.
#   docker build --target test -t moneyfast-orchestrator:test .
# ---------------------------------------------------------------------------
FROM base AS test

RUN apt-get update \
 && apt-get install -y --no-install-recommends make \
 && rm -rf /var/lib/apt/lists/*

COPY requirements-test.txt pytest.ini .coveragerc Makefile ./
RUN pip install --no-cache-dir -r requirements-test.txt

COPY tests/ ./tests/

# `get_llm` needs a key on its FIRST CALL (not at import — the import is lazy
# for exactly that reason). A dummy value is enough: the suite blocks sockets,
# so no request can leave the container even if a mock were missed.
#
# Both names: the suite's own fixture sets the provider-specific one, and
# `LLM_API_KEY` is what a container gets from compose.
ENV GROQ_API_KEY=test-key-not-used \
    LLM_API_KEY=test-key-not-used \
    MCP_SERVER_URL=http://mcp-market-data:8000/sse

# Runs as root on purpose: this stage writes coverage artefacts and never ships.
RUN make test

# ---------------------------------------------------------------------------
# Stage 3: runtime. What actually ships. Identical to the original image.
# ---------------------------------------------------------------------------
FROM base AS runtime

RUN useradd --create-home --uid 10001 appuser \
 && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8080/healthz || exit 1

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8080"]
