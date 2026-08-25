# MoneyFast data ingestor. No exposed port: it makes requests, it does not
# serve them.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Europe/Istanbul

WORKDIR /app

# tzdata: the quote schedule is expressed in Europe/Istanbul, and zoneinfo
# has no database to read without it in a slim image.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY ingestor/ ./ingestor/

# ---------------------------------------------------------------------------
# Stage 2: test.
#   docker build --target test -t moneyfast-ingestor:test .
# ---------------------------------------------------------------------------
FROM base AS test

RUN apt-get update \
 && apt-get install -y --no-install-recommends make \
 && rm -rf /var/lib/apt/lists/*

COPY requirements-test.txt pytest.ini .coveragerc Makefile ./
RUN pip install --no-cache-dir -r requirements-test.txt
COPY tests/ ./tests/
RUN make test

# ---------------------------------------------------------------------------
# Stage 3: runtime.
# ---------------------------------------------------------------------------
FROM base AS runtime

RUN useradd --create-home --uid 10004 ingestuser \
 && chown -R ingestuser:ingestuser /app
USER ingestuser

CMD ["python", "-m", "ingestor.run"]
