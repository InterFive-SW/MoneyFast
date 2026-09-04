"""The startup wiring that gives the SSE fan-out a database reader.

Injected at startup rather than imported inside the stream module, so that
module carries no database dependency and stays testable without a session.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

NOW = datetime.now(timezone.utc)


@pytest.fixture
def reader(mocker):
    """Install the startup hook against a stubbed session and return the
    frame-reading callable it configured."""
    from app.modules.investment import market_service
    from app.modules.market import stream

    captured = {}
    mocker.patch.object(stream, "configure", side_effect=lambda fn: captured.setdefault("fn", fn))
    mocker.patch("app.core.database.SessionLocal", return_value=MagicMock())
    mocker.patch.object(
        market_service, "latest_quotes",
        return_value={"THYAO": {"price": 304.0, "change_amount": 3.0,
                                "change_percent": 1.0, "received_at": NOW}},
    )
    mocker.patch.object(market_service, "freshness", return_value=(NOW, 15, True, False))

    import app.main as main

    main.configure_market_stream()
    return captured["fn"]


class TestReadFrame:
    def test_projects_quotes_into_a_frame(self, reader):
        frame = reader()
        assert frame["quotes"]["THYAO"]["price"] == 304.0
        assert frame["quotes"]["THYAO"]["changePercent"] == 1.0

    def test_carries_the_freshness_the_contract_requires(self, reader):
        """A price without its as_of is a price presented as current."""
        frame = reader()
        assert frame["delay_minutes"] == 15
        assert frame["is_delayed"] is True
        assert frame["as_of"].startswith(NOW.strftime("%Y-%m-%d"))

    def test_no_quotes_yields_a_null_as_of_rather_than_now(self, reader, mocker):
        from app.modules.investment import market_service

        mocker.patch.object(market_service, "latest_quotes", return_value={})
        mocker.patch.object(market_service, "freshness", return_value=(None, 0, True, True))
        frame = reader()
        assert frame["as_of"] is None
        assert frame["quotes"] == {}

    def test_the_session_is_closed_even_when_the_read_fails(self, mocker):
        """A leaked session per poll would exhaust the pool within an hour."""
        from app.modules.investment import market_service
        from app.modules.market import stream

        session = MagicMock()
        captured = {}
        mocker.patch.object(stream, "configure", side_effect=lambda fn: captured.setdefault("fn", fn))
        mocker.patch("app.core.database.SessionLocal", return_value=session)
        mocker.patch.object(market_service, "latest_quotes", side_effect=RuntimeError("db down"))

        import app.main as main

        main.configure_market_stream()
        with pytest.raises(RuntimeError):
            captured["fn"]()
        assert session.close.called
