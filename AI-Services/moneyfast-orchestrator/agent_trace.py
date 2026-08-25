"""Agent trace recorder.

The orchestrator logged prose to stdout — `routed intent=… agent=…` and
`compliance verdict=…` — with no timing anywhere, no record of what each agent
received or returned, and nothing that outlived a container rebuild. There was
no way to answer "which agent is slow" or "what did the transaction agent
actually get".

This writes one JSON object per line to a dated file, from two hook points:
every graph node, and every MCP tool call. That is enough to reconstruct a
whole turn — who ran, in what order, for how long, on what input.

Two rules this module lives by:

1. **It must never break a turn.** Every entry point swallows its own
   exceptions. Diagnostics that can take down the thing they are watching are
   worse than no diagnostics.
2. **It must never guess.** A payload that will not serialise is recorded as
   its `repr`, not dropped and not summarised into something that reads like a
   value it is not.

Payloads are recorded IN FULL, which is a deliberate choice: the data here is
synthetic (see CLAUDE.md) and complete payloads are what make a turn
replayable. The trace directory is gitignored for the same reason.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("moneyfast.trace")

#: Off with AGENT_TRACE=0. One setting, no code change.
ENABLED = os.getenv("AGENT_TRACE", "1") not in ("0", "false", "False", "")

#: Bind-mounted to ./traces on the host; see infra/docker-compose.yml. Without
#: the mount the file lives only inside the container and dies on rebuild.
TRACE_DIR = Path(os.getenv("AGENT_TRACE_DIR", "/app/traces"))

#: The turn a record belongs to. A tool call cannot see graph state, so the id
#: travels through a context variable — the standard way to carry correlation
#: across an async boundary without threading a parameter through every layer.
_trace_id: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="")
_thread_id: contextvars.ContextVar[str] = contextvars.ContextVar("thread_id", default="")

#: Set once the directory has proved unwritable, so a broken mount costs one
#: warning rather than one per record for the life of the process.
_disabled_reason: Optional[str] = None


def new_turn(thread_id: str = "") -> str:
    """Start a turn and return its trace id."""
    turn = uuid.uuid4().hex[:16]
    _trace_id.set(turn)
    _thread_id.set(thread_id or "")
    return turn


def current_trace_id() -> str:
    return _trace_id.get()


def _encode(value: Any) -> Any:
    """JSON-safe, without ever raising.

    `default=repr` catches datetimes, exceptions and anything else the graph
    puts in state. A record with a `repr` in it is still useful; a record that
    raised is not.
    """
    try:
        return json.loads(json.dumps(value, default=repr, ensure_ascii=False))
    except (TypeError, ValueError):
        return repr(value)


def record(kind: str, name: str, ms: float, status: str, **fields: Any) -> None:
    """Append one record. Never raises."""
    global _disabled_reason
    if not ENABLED or _disabled_reason:
        return

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "trace_id": _trace_id.get(),
        "thread_id": _thread_id.get(),
        "kind": kind,
        "name": name,
        "ms": round(ms, 1),
        "status": status,
    }
    for key, value in fields.items():
        entry[key] = _encode(value)

    try:
        TRACE_DIR.mkdir(parents=True, exist_ok=True)
        path = TRACE_DIR / f"agent-trace-{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        # An unwritable mount disables tracing for the process rather than
        # failing every turn that follows.
        _disabled_reason = str(exc)
        log.warning("agent trace disabled, cannot write to %s: %s", TRACE_DIR, exc)


class span:
    """Time a block and record it, whatever happens inside.

    Used as a context manager so a raising node is still recorded — with its
    duration and the exception — instead of vanishing from the trace exactly
    when it is most interesting.
    """

    def __init__(self, kind: str, name: str, **fields: Any) -> None:
        self.kind = kind
        self.name = name
        self.fields = fields
        self.started = 0.0

    def __enter__(self) -> "span":
        self.started = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, _tb) -> bool:
        ms = (time.perf_counter() - self.started) * 1000
        if exc is None:
            record(self.kind, self.name, ms, "ok", **self.fields)
        else:
            record(
                self.kind, self.name, ms, "error",
                error=f"{exc.__class__.__name__}: {exc}", **self.fields,
            )
        return False  # never swallow the caller's exception

    def set(self, **fields: Any) -> None:
        """Attach fields discovered inside the block, e.g. the output."""
        self.fields.update(fields)
