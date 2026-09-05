"""NAV geri doldurma.

Korunan asıl iddia: **parça parça yazıyor.** `run_tefas` bütün serileri
bellekte biriktirip en sonda tek seferde yazıyordu ve ölçüldü -- on üç
dakika sonra süreç öldüğünde veritabanına hiçbir şey yazılmamıştı. Saatlerce
süren bir işin tamamı sonundaki tek yazmaya bağlı olamaz.
"""

from __future__ import annotations

import httpx
import pytest

from ingestor import backfill_funds, sinks
from ingestor.sources import tefas_source


@pytest.fixture
def wired(monkeypatch):
    """Ağ yok: kapsam ve yazma taklit ediliyor, çekme sayılıyor."""
    state = {"asked": [], "pushes": []}

    monkeypatch.setattr(
        tefas_source, "fetch_prices",
        lambda code, client: (
            state["asked"].append(code)
            or ([{"code": code, "as_of": "2026-09-04", "price": 1.0}],
                {"code": code, "category_rank": 1, "category_size": 10})
        ),
    )
    monkeypatch.setattr(
        sinks, "push_funds_to_backend",
        lambda client, funds, prices=None: state["pushes"].append(len(prices or []))
        or {"funds_written": 0, "prices_written": len(prices or [])},
    )
    monkeypatch.setattr(httpx, "Client", lambda **kw: _NullClient())
    return state


class _NullClient:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def coverage(monkeypatch, codes):
    monkeypatch.setattr(
        sinks, "fetch_fund_coverage", lambda client: {"missing_prices": list(codes)},
    )


class TestIncremental:
    def test_it_writes_per_chunk_not_once_at_the_end(self, wired, monkeypatch):
        """Süreç ölürse o ana kadarki iş DURMALI."""
        coverage(monkeypatch, [f"F{i:03d}" for i in range(backfill_funds.CHUNK * 2)])
        backfill_funds.backfill(None)
        assert len(wired["pushes"]) == 2

    def test_every_missing_fund_is_asked_once(self, wired, monkeypatch):
        coverage(monkeypatch, ["AAL", "AAS", "AAV"])
        result = backfill_funds.backfill(None)
        assert wired["asked"] == ["AAL", "AAS", "AAV"]
        assert result == {"funds": 3, "rows": 3}

    def test_a_limit_bounds_the_run(self, wired, monkeypatch):
        """Elle bir deneme turunda saatlerce beklememek için."""
        coverage(monkeypatch, ["A", "B", "C", "D"])
        assert backfill_funds.backfill(None, limit=2)["funds"] == 2
        assert wired["asked"] == ["A", "B"]

    def test_nothing_missing_writes_nothing(self, wired, monkeypatch):
        coverage(monkeypatch, [])
        assert backfill_funds.backfill(None) == {"funds": 0, "rows": 0}
        assert wired["pushes"] == []

    def test_an_unavailable_coverage_endpoint_is_not_fatal(self, wired, monkeypatch):
        monkeypatch.setattr(sinks, "fetch_fund_coverage", lambda client: {})
        assert backfill_funds.backfill(None) == {"funds": 0, "rows": 0}

    def test_a_fund_with_no_series_is_counted_but_not_pushed(self, monkeypatch):
        """Serisi boş dönen fon ilerlemeyi durdurmuyor: kapsamda kalıyor ve
        bir sonraki tur yeniden deniyor."""
        monkeypatch.setattr(tefas_source, "fetch_prices", lambda code, client: ([], None))
        pushed = []
        monkeypatch.setattr(
            sinks, "push_funds_to_backend",
            lambda client, funds, prices=None: pushed.append(1) or {},
        )
        monkeypatch.setattr(httpx, "Client", lambda **kw: _NullClient())
        coverage(monkeypatch, ["AAL"])
        assert backfill_funds.backfill(None) == {"funds": 1, "rows": 0}
        assert pushed == []


class TestEntryPoint:
    def test_it_runs_without_arguments(self, wired, monkeypatch):
        coverage(monkeypatch, ["AAL"])
        assert backfill_funds.main([]) == 0

    def test_a_positional_limit_is_honoured(self, wired, monkeypatch):
        coverage(monkeypatch, ["AAL", "AAS"])
        assert backfill_funds.main(["1"]) == 0
        assert wired["asked"] == ["AAL"]
