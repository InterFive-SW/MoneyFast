# MCP tool server, SSE transport on 8000.
# Multi-stage: the `test` stage runs the unit suite and the 100% coverage gate;
# the `runtime` stage ships without pytest, make, or the tests directory.

# ---------------------------------------------------------------------------
# Stage 1: base. Runtime deps only, shared by both downstream stages.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

RUN pip install "mcp>=1.9,<2" "uvicorn[standard]>=0.32,<0.40" "httpx>=0.27,<0.29"

COPY . /app

# ---------------------------------------------------------------------------
# Stage 2: test. Fails the build when a test fails or coverage drops below 100.
# Build it explicitly in CI:  docker build --target test -t moneyfast-mcp:test .
# ---------------------------------------------------------------------------
FROM base AS test

RUN apt-get update \
 && apt-get install -y --no-install-recommends make \
 && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -r requirements-test.txt

# Runs as root here on purpose: this stage writes htmlcov/ and coverage.xml,
# and it is never shipped.
RUN make test

# ---------------------------------------------------------------------------
# Stage 3: runtime. What actually ships.
# ---------------------------------------------------------------------------
FROM base AS runtime

# Keep the image lean and the attack surface small: no tests, no pytest, no make.
RUN rm -rf /app/tests /app/requirements-test.txt /app/Makefile \
           /app/htmlcov /app/coverage.xml /app/.pytest_cache /app/.coverage

RUN useradd --create-home --uid 10002 mcpuser && chown -R mcpuser:mcpuser /app
USER mcpuser

EXPOSE 8000
CMD ["python", "server.py"]
