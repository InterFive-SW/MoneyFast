"""Portföye dokunan haberler: hangi haberin kime ait olduğu.

Bu panelin tek işi, kullanıcının GERÇEKTEN tuttuğu hisselere bağlı haberleri
listelemek. Yorum yok, duygu puanı yok -- başlık, kaynak ve tarih. Testler bu
sınırı da sabitliyor: `sentiment` her satırda `neutral` kalmalı.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user_id
from app.main import app
from app.modules.investment import market_service
from app.modules.market import service as news_service

URL = "/api/market/news/portfolio"


def _row(item_id, symbols, title="Başlık", days_ago=1, source="Test Kaynağı"):
    return SimpleNamespace(
        id=item_id,
        source=source,
        title=title,
        url=f"https://example.com/{item_id}",
        published_at=datetime.now(timezone.utc) - timedelta(days=days_ago),
        related_symbols=list(symbols),
    )


def _db_returning(rows):
    """`portfolio_news`'in okuduğu zincir: query().filter().order_by().all()."""
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = rows
    return db


class TestPortfolioNews:
    def test_counts_and_headlines_come_from_one_read(self):
        rows = [_row("a", ["AKBNK"]), _row("b", ["AKBNK", "THYAO"])]
        items, counts = news_service.portfolio_news(_db_returning(rows), ["AKBNK", "AEFES"])
        assert [item.id for item in items] == ["a", "b"]
        assert counts == {"AKBNK": 2, "AEFES": 0}

    def test_a_symbol_outside_the_portfolio_is_not_counted(self):
        """Haber THYAO'yu da anıyor ama kullanıcı THYAO tutmuyor."""
        _, counts = news_service.portfolio_news(
            _db_returning([_row("a", ["AKBNK", "THYAO"])]), ["AKBNK"]
        )
        assert counts == {"AKBNK": 1}

    def test_a_held_symbol_with_no_news_is_reported_as_zero(self):
        """Sıfır, listeden düşmenin değil, sayılmanın sonucudur: kullanıcı o
        hissesi için haber OLMADIĞINI görmeli."""
        _, counts = news_service.portfolio_news(_db_returning([]), ["DOAS"])
        assert counts == {"DOAS": 0}

    def test_the_limit_trims_headlines_but_not_counts(self):
        rows = [_row(str(index), ["AKBNK"]) for index in range(5)]
        items, counts = news_service.portfolio_news(_db_returning(rows), ["AKBNK"], limit=2)
        assert len(items) == 2
        assert counts == {"AKBNK": 5}

    def test_an_empty_portfolio_reads_nothing(self):
        """Boş bir sembol listesiyle sorgu, TÜM haberlerle örtüşürdü."""
        db = _db_returning([_row("a", ["AKBNK"])])
        assert news_service.portfolio_news(db, []) == ([], {})
        assert not db.query.called

    def test_duplicate_and_blank_symbols_are_dropped(self):
        db = _db_returning([])
        _, counts = news_service.portfolio_news(db, ["AKBNK", "AKBNK", ""])
        assert counts == {"AKBNK": 0}

    def test_a_missing_symbol_list_on_a_row_does_not_crash(self):
        _, counts = news_service.portfolio_news(
            _db_returning([_row("a", [])]), ["AKBNK"]
        )
        assert counts == {"AKBNK": 0}

    @pytest.mark.parametrize("days", [0, -5])
    def test_a_non_positive_window_is_clamped_to_a_day(self, days):
        """Sıfır gün, `now()`'dan sonra yayımlanmış haber demek olurdu."""
        db = _db_returning([])
        news_service.portfolio_news(db, ["AKBNK"], days=days)
        assert db.query.called


class TestHeldSymbols:
    def test_symbols_keep_their_order_and_are_deduplicated(self):
        holdings = [
            {"symbol": "THYAO", "quantity": 10},
            {"symbol": "AKBNK", "quantity": 5},
            {"symbol": "THYAO", "quantity": 3},
        ]
        assert news_service.held_symbols(holdings) == ["THYAO", "AKBNK"]

    def test_a_closed_position_is_not_held(self):
        """Sattığın hissenin haberi portföyüne dokunmuyor."""
        assert news_service.held_symbols([{"symbol": "THYAO", "quantity": 0}]) == []

    def test_a_row_without_a_symbol_is_skipped(self):
        assert news_service.held_symbols([{"quantity": 5}, {"symbol": None}]) == []

    def test_a_missing_quantity_is_not_a_holding(self):
        assert news_service.held_symbols([{"symbol": "THYAO"}]) == []


@pytest.fixture
def as_user(client):
    """Oturum sahibi user-1 olan bir istemci."""
    app.dependency_overrides[get_current_user_id] = lambda: "user-1"
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_current_user_id, None)


@pytest.fixture
def portfolio(mocker):
    mocker.patch.object(
        market_service, "holdings",
        return_value=[
            {"symbol": "AKBNK", "name": "Akbank T.A.Ş.", "quantity": 100},
            {"symbol": "DOAS", "name": "Doğuş Otomotiv", "quantity": 10},
        ],
    )


class TestEndpoint:
    def test_the_panel_reports_every_holding_even_the_quiet_ones(
        self, as_user, portfolio, mocker
    ):
        mocker.patch.object(
            news_service, "portfolio_news",
            return_value=([_row("a", ["AKBNK", "THYAO"], title="Akbank...")], {"AKBNK": 1, "DOAS": 0}),
        )
        body = as_user.get(URL).json()
        assert [(s["symbol"], s["count"]) for s in body["symbols"]] == [("AKBNK", 1), ("DOAS", 0)]
        assert body["windowDays"] == news_service.NEWS_WINDOW_DAYS

    def test_an_item_says_which_of_the_holdings_it_touches(
        self, as_user, portfolio, mocker
    ):
        """Haber THYAO'yu da anıyor; panelde AKBNK yüzünden duruyor ve bunun
        okunabilir olması gerekiyor."""
        mocker.patch.object(
            news_service, "portfolio_news",
            return_value=([_row("a", ["AKBNK", "THYAO"])], {"AKBNK": 1, "DOAS": 0}),
        )
        item = as_user.get(URL).json()["items"][0]
        assert item["relatedSymbols"] == ["AKBNK", "THYAO"]
        assert item["heldSymbols"] == ["AKBNK"]

    def test_nothing_is_interpreted(self, as_user, portfolio, mocker):
        """Bir başlığın olumlu ya da olumsuz olduğu bir piyasa görüşüdür."""
        mocker.patch.object(
            news_service, "portfolio_news",
            return_value=([_row("a", ["AKBNK"])], {"AKBNK": 1, "DOAS": 0}),
        )
        assert as_user.get(URL).json()["items"][0]["sentiment"] == "neutral"

    def test_an_item_carries_its_date_as_well_as_its_age(
        self, as_user, portfolio, mocker
    ):
        mocker.patch.object(
            news_service, "portfolio_news",
            return_value=([_row("a", ["AKBNK"], days_ago=2)], {"AKBNK": 1, "DOAS": 0}),
        )
        item = as_user.get(URL).json()["items"][0]
        assert item["publishedAt"].startswith("20")
        assert "önce" in item["time"]

    def test_a_source_without_a_link_still_renders(self, as_user, portfolio, mocker):
        row = _row("a", ["AKBNK"])
        row.url = None
        mocker.patch.object(
            news_service, "portfolio_news", return_value=([row], {"AKBNK": 1, "DOAS": 0})
        )
        assert as_user.get(URL).json()["items"][0]["url"] == "#"

    def test_an_empty_portfolio_returns_an_empty_body_not_an_error(
        self, as_user, mocker
    ):
        mocker.patch.object(market_service, "holdings", return_value=[])
        mocker.patch.object(news_service, "portfolio_news", return_value=([], {}))
        body = as_user.get(URL).json()
        assert body == {"symbols": [], "items": [], "windowDays": news_service.NEWS_WINDOW_DAYS}

    def test_the_window_can_be_narrowed_and_is_echoed_back(
        self, as_user, portfolio, mocker
    ):
        read = mocker.patch.object(news_service, "portfolio_news", return_value=([], {}))
        body = as_user.get(URL, params={"days": 7}).json()
        assert body["windowDays"] == 7
        assert read.call_args.kwargs["days"] == 7

    def test_an_anonymous_caller_is_refused(self, client):
        """Demo portföyüne düşmüyor: başkasının hisselerinin haberlerini
        "portföyünüze dokunan haberler" diye göstermek, izleme listesinin
        eskiden yaptığı hatanın aynısı olurdu."""
        assert client.get(URL).status_code == 401


class TestAgentEndpoint:
    """MCP yolu: kullanıcı doğrulanmış oturum zarfından gelip yola konuyor."""

    def test_the_user_comes_from_the_path(self, client, mocker):
        holdings = mocker.patch.object(market_service, "holdings", return_value=[])
        mocker.patch.object(news_service, "portfolio_news", return_value=([], {}))
        app.dependency_overrides[get_db] = lambda: MagicMock(spec=Session)
        try:
            response = client.get(f"{URL}/user-42")
        finally:
            app.dependency_overrides.pop(get_db, None)
        assert response.status_code == 200
        assert holdings.call_args.kwargs["user_id"] == "user-42"

    def test_the_key_names_are_the_mcp_contract_surface(self, client, mocker):
        """`get_portfolio_news`'in `_normalize`'ı bu adları İSİMLE arıyor ve
        eksiğinde `ContractViolationError` fırlatıyor.

        Bu yüzden burada pinleniyorlar. Şemadaki bir yeniden adlandırma
        backend testlerinden geçer, MCP testleri sahte bir gövdeye baktığı
        için oradan da geçer, ve yalnızca canlı sistemde -- ajanın "haberlere
        ulaşamadım" demesiyle -- görünürdü.
        """
        mocker.patch.object(
            market_service, "holdings",
            return_value=[{"symbol": "AKBNK", "name": "Akbank", "quantity": 1}],
        )
        mocker.patch.object(
            news_service, "portfolio_news",
            return_value=([_row("a", ["AKBNK"])], {"AKBNK": 1}),
        )
        app.dependency_overrides[get_db] = lambda: MagicMock(spec=Session)
        try:
            body = client.get(f"{URL}/user-1").json()
        finally:
            app.dependency_overrides.pop(get_db, None)

        assert set(body) == {"symbols", "items", "windowDays"}
        assert set(body["symbols"][0]) == {"symbol", "name", "count"}
        assert {"id", "title", "source", "publishedAt", "url",
                "heldSymbols", "relatedSymbols"} <= set(body["items"][0])

    def test_both_endpoints_answer_from_the_same_helper(self, as_user, portfolio, mocker):
        """Panel ile sohbetin kullanıcının neye sahip olduğu konusunda
        ayrışması mümkün olmamalı."""
        mocker.patch.object(
            news_service, "portfolio_news",
            return_value=([_row("a", ["AKBNK"])], {"AKBNK": 1, "DOAS": 0}),
        )
        assert as_user.get(URL).json() == as_user.get(f"{URL}/user-1").json()
