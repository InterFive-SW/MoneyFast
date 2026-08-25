"""The trace recorder.

Its whole value is being there when something goes wrong, so the properties
worth pinning are the defensive ones: it must not raise, must not lose a
record it claimed to write, and must never be able to take down the turn it is
observing.
"""

from __future__ import annotations

import json

import pytest

import agent_trace


@pytest.fixture()
def trace_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_trace, "TRACE_DIR", tmp_path)
    monkeypatch.setattr(agent_trace, "ENABLED", True)
    monkeypatch.setattr(agent_trace, "_disabled_reason", None)
    return tmp_path


def read(directory):
    files = list(directory.glob("*.jsonl"))
    if not files:
        return []
    return [json.loads(line) for line in files[0].read_text().splitlines()]


class TestRecord:
    def test_writes_one_json_object_per_line(self, trace_dir):
        agent_trace.record("node", "router", 12.3, "ok", input={"a": 1})
        agent_trace.record("tool", "get_market_data", 40.0, "ok")
        rows = read(trace_dir)
        assert [r["name"] for r in rows] == ["router", "get_market_data"]
        assert rows[0]["kind"] == "node"
        assert rows[0]["ms"] == 12.3

    def test_carries_the_turns_correlation_ids(self, trace_dir):
        agent_trace.new_turn("thread-9")
        agent_trace.record("node", "router", 1.0, "ok")
        row = read(trace_dir)[0]
        assert row["trace_id"] == agent_trace.current_trace_id()
        assert row["thread_id"] == "thread-9"

    def test_a_new_turn_gets_a_new_id(self, trace_dir):
        first = agent_trace.new_turn("t")
        assert agent_trace.new_turn("t") != first

    def test_disabled_writes_nothing(self, trace_dir, monkeypatch):
        monkeypatch.setattr(agent_trace, "ENABLED", False)
        agent_trace.record("node", "router", 1.0, "ok")
        assert read(trace_dir) == []


class TestNeverBreaksTheTurn:
    def test_an_unserialisable_payload_is_kept_as_repr(self, trace_dir):
        """Dropping it would lose the record; raising would lose the turn."""
        class Opaque:
            def __repr__(self): return "<Opaque>"

        agent_trace.record("node", "router", 1.0, "ok", input={"obj": Opaque()})
        assert "<Opaque>" in json.dumps(read(trace_dir)[0])

    def test_a_self_referencing_payload_does_not_raise(self, trace_dir):
        loop: dict = {}
        loop["self"] = loop
        agent_trace.record("node", "router", 1.0, "ok", input=loop)
        assert len(read(trace_dir)) == 1

    def test_an_unwritable_directory_disables_tracing_once(self, tmp_path, monkeypatch, caplog):
        """One warning, not one per record for the life of the process."""
        monkeypatch.setattr(agent_trace, "TRACE_DIR", tmp_path / "nope")
        monkeypatch.setattr(agent_trace, "ENABLED", True)
        monkeypatch.setattr(agent_trace, "_disabled_reason", None)
        monkeypatch.setattr(
            agent_trace.Path, "mkdir",
            lambda *a, **k: (_ for _ in ()).throw(OSError("read-only")),
        )
        with caplog.at_level("WARNING"):
            agent_trace.record("node", "router", 1.0, "ok")
            agent_trace.record("node", "synthesis", 1.0, "ok")
        assert caplog.text.count("agent trace disabled") == 1


class TestSpan:
    def test_records_duration_and_output(self, trace_dir):
        with agent_trace.span("node", "router", input={"q": 1}) as sp:
            sp.set(output={"target_agent": "PORTFOLIO_AGENT"})
        row = read(trace_dir)[0]
        assert row["status"] == "ok"
        assert row["output"] == {"target_agent": "PORTFOLIO_AGENT"}
        assert row["ms"] >= 0

    def test_a_raising_block_is_still_recorded(self, trace_dir):
        """A node that blows up is exactly when the trace matters most."""
        with pytest.raises(ValueError):
            with agent_trace.span("node", "synthesis"):
                raise ValueError("groq exploded")
        row = read(trace_dir)[0]
        assert row["status"] == "error"
        assert "groq exploded" in row["error"]

    def test_the_exception_still_propagates(self, trace_dir):
        with pytest.raises(RuntimeError):
            with agent_trace.span("tool", "x"):
                raise RuntimeError("boom")
