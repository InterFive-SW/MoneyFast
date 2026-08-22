# filename: embeddings.py
"""Local, free embedding generation.

The model is `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
executed through fastembed on ONNX Runtime. Three properties matter and each one is why an API-backed
provider was rejected:

* No API key exists anywhere in this system, so there is no secret to leak
  through SQL, Compose, or a log line, and no quota to exhaust mid-demo.
* No network egress. The `rag` container never joins `ai-egress`; the model
  weights are baked into the image at build time (see the Dockerfile), so a
  cold start does not depend on Hugging Face being reachable.
* Deterministic. The same text produces the same vector on every run, which
  is what makes retrieval regressions reproducible.

Some model families are asymmetric and want a prefix on the input ("query: "
on a search string, "passage: " on a stored chunk); others are symmetric and
are actively hurt by one, because they never saw those tokens in training.
That makes prefixing a property of the model, not of the call site, so it is
resolved from the configured model name rather than passed in. The two public
functions stay separate regardless: the caller always knows whether it is
embedding a question or a document, and that is the information the prefix
rule needs.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Iterable, Sequence

log = logging.getLogger("moneyfast.rag.embeddings")

#: The only 384-dimension multilingual model fastembed ships. Apache-2.0,
#: ~0.22GB of ONNX weights, good Turkish coverage. fastembed does not support
#: intfloat/multilingual-e5-small at all -- its smallest E5 is
#: multilingual-e5-large at 1024 dimensions and 2.24GB, which would mean a
#: schema change and a ten-fold larger image for no retrieval gain at this
#: corpus size.
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_DIMENSION = 384

#: Model families that expect asymmetric input prefixes, matched on a
#: substring so a version bump inside a family keeps working. Anything not
#: listed is treated as symmetric and gets no prefix -- the safe default,
#: because a spurious prefix costs recall on a symmetric model.
_PREFIX_RULES = (
    ("-e5-", ("query: ", "passage: ")),
    ("bge-", ("Represent this sentence for searching relevant passages: ", "")),
)
NO_PREFIX = ("", "")

_model = None
_lock = threading.Lock()


def model_name() -> str:
    return os.getenv("EMBEDDING_MODEL", DEFAULT_MODEL)


def dimension() -> int:
    raw = os.getenv("EMBEDDING_DIMENSION")
    if raw is None:
        return DEFAULT_DIMENSION
    try:
        return int(raw)
    except ValueError:
        log.warning("EMBEDDING_DIMENSION=%r is not an integer, using %s", raw, DEFAULT_DIMENSION)
        return DEFAULT_DIMENSION


def get_model():
    """Load the ONNX model once, on first use.

    Guarded by a lock because uvicorn serves concurrently and fastembed's
    loader is not reentrant; two simultaneous cold requests would otherwise
    each pay the load cost and one would win the assignment.
    """
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                from fastembed import TextEmbedding

                name = model_name()
                log.info("loading embedding model %s", name)
                _model = TextEmbedding(model_name=name)
    return _model


def _encode(texts: Sequence[str]) -> list[list[float]]:
    vectors = [list(map(float, v)) for v in get_model().embed(list(texts))]
    expected = dimension()
    for vector in vectors:
        if len(vector) != expected:
            # A dimension mismatch is caught here rather than by the Postgres
            # VECTOR(384) column, because the database error names neither the
            # model nor the configured dimension.
            raise ValueError(
                f"model {model_name()} produced {len(vector)} dimensions, "
                f"EMBEDDING_DIMENSION is {expected}"
            )
    return vectors


def prefixes() -> tuple[str, str]:
    """(query_prefix, passage_prefix) for the configured model."""
    name = model_name().lower()
    for marker, pair in _PREFIX_RULES:
        if marker in name:
            return pair
    return NO_PREFIX


def embed_query(text: str) -> list[float]:
    """Embed a search string, with whatever prefix the model expects."""
    return _encode([f"{prefixes()[0]}{text}"])[0]


def embed_passages(texts: Iterable[str]) -> list[list[float]]:
    """Embed documents for storage, with whatever prefix the model expects."""
    items = list(texts)
    if not items:
        return []
    prefix = prefixes()[1]
    return _encode([f"{prefix}{text}" for text in items])


def to_pgvector(vector: Sequence[float]) -> str:
    """Render a vector as the literal pgvector accepts: `[0.1,0.2,...]`."""
    return "[" + ",".join(repr(float(value)) for value in vector) + "]"
