"""Bekleyen limit emirlerinin eşleştirilmesi.

Buradaki iddiaların hepsi tek bir ayrımın etrafında: limit fiyat bir
FİYATLAMA girdisi değil, bir TETİKLEYİCİ. Eskiden `ai_service._estimate`
limit fiyatı gördüğünde onu referans fiyatın yerine koyuyordu, dolayısıyla
bir limit emri piyasa ne olursa olsun kullanıcının yazdığı fiyattan ANINDA
gerçekleşiyordu.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.investment import ai_service, matching, market_service, service
from app.modules.investment.models import InvestmentProduct, TransactionProposal
from app.modules.market.models import Fund

NOW = datetime.now(timezone.utc)
TODAY = NOW.date()


def proposal(**overrides):
    row = SimpleNamespace(
        id="PROP-1",
        user_id="user-1",
        status=matching.WAITING_PRICE,
        transaction_type="BUY",
        symbol="THYAO",
        quantity=10.0,
        limit_price=290.0,
        # Tahmin ELLE yazılmıyor: sistemin kendi fiyatlaması kullanılıyor,
        # yoksa "limitten dolarsa fark sıfır" iddiası uydurma bir sayıya
        # dayanırdı.
        payload={"estimate": ai_service.reprice_estimate(
            {"currency": "TRY", "fx": None}, "BUY", 10.0, 290.0
        )},
        confirmed_at=None,
        created_at=NOW - timedelta(hours=1),
    )
    for key, value in overrides.items():
        setattr(row, key, value)
    return row


def account(cash=100_000.0):
    return SimpleNamespace(
        id="acct-1", cash_balance=cash, currency_code="TRY",
        account_number="TR-TEST-0001",
    )


class FakeQuery:
    """Süzgeçleri yok sayıp önceden verilmiş satırları döner.

    Süzgeçlerin kendisi burada test edilmiyor: bunlar SQLAlchemy ifadeleri ve
    onları taklit etmek, taklidi test etmek olurdu. Test edilen şey, dönen
    satırlarla ne YAPILDIĞI.
    """

    def __init__(self, rows):
        self._rows = rows

    def filter(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self._rows)


class FakeDB:
    def __init__(self, waiting=(), products=(), funds=(), pending=()):
        self._by_model = {
            TransactionProposal: list(waiting) or list(pending),
            InvestmentProduct: list(products),
            Fund: list(funds),
        }
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def query(self, model):
        return FakeQuery(self._by_model.get(model, []))

    def execute(self, *_args, **_kwargs):  # pragma: no cover - kullanılmıyor
        raise AssertionError("execute beklenmiyor")

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def get(self, _model, _key):  # pragma: no cover - testte patch'leniyor
        return None


class TestMatchRule:
    @pytest.mark.parametrize("kind,market,limit,expected", [
        ("BUY", 289.0, 290.0, True),
        ("BUY", 290.0, 290.0, True),
        ("BUY", 291.0, 290.0, False),
        ("SELL", 311.0, 310.0, True),
        ("SELL", 310.0, 310.0, True),
        ("SELL", 309.0, 310.0, False),
    ])
    def test_direction_decides_the_comparison(self, kind, market, limit, expected):
        assert matching.is_match(kind, market, limit) is expected

    def test_an_unknown_direction_never_matches(self):
        """Bilinmeyen bir tür için "eşleşti" demek, tanımlanmamış bir işlemi
        uygulamak olurdu."""
        assert matching.is_match("TRANSFER", 1.0, 1.0) is False


class TestFundPrice:
    def test_a_current_nav_is_used(self):
        fund = SimpleNamespace(price=12.5, as_of=TODAY)
        assert matching._fund_price(fund, TODAY) == 12.5

    @pytest.mark.parametrize("fund", [
        None,
        SimpleNamespace(price=None, as_of=TODAY),
        SimpleNamespace(price=12.5, as_of=None),
    ])
    def test_an_unknown_nav_refuses_rather_than_guessing(self, fund):
        assert matching._fund_price(fund, TODAY) is None

    def test_an_ancient_nav_is_refused(self):
        """Aylık eski bir NAV, o fiyattan bir işlem uydurmak demek."""
        old = TODAY - timedelta(days=matching.FUND_NAV_MAX_AGE_DAYS + 1)
        assert matching._fund_price(SimpleNamespace(price=12.5, as_of=old), TODAY) is None

    def test_a_weekend_gap_is_still_acceptable(self):
        """Fon hafta sonu fiyat yayımlamıyor; bu bir arıza değil."""
        friday = TODAY - timedelta(days=3)
        assert matching._fund_price(SimpleNamespace(price=12.5, as_of=friday), TODAY) == 12.5


class TestStockPrice:
    def product(self, market="BIST"):
        return SimpleNamespace(market=market, product_type="stock")

    def test_a_fresh_quote_on_an_open_market_is_used(self):
        quotes = {"THYAO": {"price": 289.0, "received_at": NOW}}
        assert matching._stock_price("THYAO", self.product(), quotes, {"BIST"}) == 289.0

    def test_no_quote_is_no_price(self):
        assert matching._stock_price("THYAO", self.product(), {}, {"BIST"}) is None

    def test_a_quote_without_a_price_is_no_price(self):
        quotes = {"THYAO": {"price": None, "received_at": NOW}}
        assert matching._stock_price("THYAO", self.product(), quotes, {"BIST"}) is None

    def test_a_closed_market_does_not_fill(self):
        """Kapalı bir piyasada "fiyat geldi" demek, olmamış bir işlemi
        uydurmak olurdu."""
        quotes = {"THYAO": {"price": 289.0, "received_at": NOW}}
        assert matching._stock_price("THYAO", self.product(), quotes, {"NASDAQ"}) is None

    def test_an_unknown_session_state_does_not_claim_closed(self):
        """`None` "hepsi kapalı" değil, "ingestor söylemiyor" demek; karar
        tazeliğe bırakılıyor."""
        quotes = {"THYAO": {"price": 289.0, "received_at": NOW}}
        assert matching._stock_price("THYAO", self.product(), quotes, None) == 289.0

    def test_a_stale_quote_does_not_fill(self):
        """Bayat bir fiyat, o fiyata gelinmiş olduğunun kanıtı değil."""
        old = NOW - timedelta(minutes=market_service.STALE_AFTER_MINUTES + 5)
        quotes = {"THYAO": {"price": 289.0, "received_at": old}}
        assert matching._stock_price("THYAO", self.product(), quotes, {"BIST"}) is None


class TestFill:
    def test_a_buy_fills_at_the_market_price_and_refunds_the_difference(self, mocker):
        """Emir limitten hazırlandı, piyasa daha ucuz: fark iade edilmezse
        kullanıcının parası eşleşmeden sonra da tutulmuş olurdu."""
        db = FakeDB()
        owner = account(cash=100_000.0)
        mocker.patch.object(market_service, "account", return_value=owner)
        finalize = mocker.patch.object(service, "finalize_settlement")
        movement = mocker.patch.object(service, "record_cash_movement")

        row = proposal()
        blocked = service._cash_amount(row.payload["estimate"], owner)
        matching.fill(db, row, 280.0)

        assert row.status == "CONFIRMED"
        assert row.confirmed_at is not None
        finalize.assert_called_once()
        # Yeniden fiyatlama gerçekten daha ucuz: 280 x 10 + masraflar.
        new_amount = service._cash_amount(row.payload["estimate"], owner)
        assert new_amount < blocked
        assert owner.cash_balance == pytest.approx(100_000.0 + (blocked - new_amount))
        movement.assert_called_once()
        assert "Fark İadesi" in movement.call_args.kwargs["description"]
        # Ve bildirim: emir GERÇEKLEŞTİ, iletildi değil.
        note = next(obj for obj in db.added if getattr(obj, "title", None))
        assert "Gerçekleşti" in note.title
        # Yön TÜRKÇE. `transaction_type.lower()` yazılıyordu ve kullanıcıya
        # "GRO buy emriniz" diye görünüyordu -- iç bir enum değeri, olduğu
        # gibi ekranda.
        assert "alış" in note.description
        assert "buy" not in note.description

    def test_a_fill_at_the_limit_moves_no_cash(self, mocker):
        """Fark kuruş altındaysa hareket yazmak, defterde anlamsız bir satır
        bırakırdı."""
        db = FakeDB()
        owner = account()
        mocker.patch.object(market_service, "account", return_value=owner)
        mocker.patch.object(service, "finalize_settlement")
        movement = mocker.patch.object(service, "record_cash_movement")

        matching.fill(db, proposal(), 290.0)
        movement.assert_not_called()

    def test_a_sell_is_repriced_without_a_cash_movement(self, mocker):
        """Satışta yerleştirme anında nakit bloke edilmiyor -- hisse bloke
        ediliyor. İade edilecek bir fark yok; dolum tutarını
        `finalize_settlement` yazıyor."""
        db = FakeDB()
        owner = account()
        mocker.patch.object(market_service, "account", return_value=owner)
        mocker.patch.object(service, "finalize_settlement")
        movement = mocker.patch.object(service, "record_cash_movement")

        row = proposal(transaction_type="SELL", limit_price=310.0)
        matching.fill(db, row, 320.0)

        movement.assert_not_called()
        assert row.payload["estimate"]["reference_price"] == 320.0

    def test_the_frozen_rate_is_carried_not_refetched(self, mocker):
        """Kullanıcı o kurla hesaplanmış bir maliyeti onayladı; günler sonra
        oynayan bir kur onayladığı tutarı sessizce değiştirirdi."""
        db = FakeDB()
        owner = account()
        mocker.patch.object(market_service, "account", return_value=owner)
        mocker.patch.object(service, "finalize_settlement")
        mocker.patch.object(service, "record_cash_movement")

        fx = {"from_currency": "USD", "to_currency": "TRY", "rate": 41.0}
        row = proposal(
            symbol="AAPL",
            payload={"estimate": {
                "net_amount": 3000.0, "currency": "USD",
                "reference_price": 300.0, "fx": fx,
            }},
            limit_price=300.0,
        )
        matching.fill(db, row, 295.0)
        assert row.payload["estimate"]["fx"] == fx

    def test_a_fill_costlier_than_the_block_is_refused(self, mocker):
        """Eşleşme kuralı bunu imkânsız kılıyor, ama olursa doğru cevap
        parayı fazladan almak değil, doldurmamak: kullanıcı en çok limit
        fiyattan hesaplanmış maliyeti onayladı."""
        mocker.patch.object(market_service, "account", return_value=account())
        finalize = mocker.patch.object(service, "finalize_settlement")
        with pytest.raises(service.SettlementError):
            matching.fill(FakeDB(), proposal(), 310.0)
        finalize.assert_not_called()

    def test_no_account_refuses_rather_than_filling(self, mocker):
        mocker.patch.object(market_service, "account", return_value=None)
        with pytest.raises(service.SettlementError):
            matching.fill(FakeDB(), proposal(), 280.0)

    def test_an_unpriceable_order_refuses_rather_than_filling(self, mocker):
        """Adet de tutar da yoksa yeniden fiyatlama None döner; sıfırlanmış
        bir tahminle doldurmak bedava bir işlem olurdu."""
        # Öneri ÖNCE kuruluyor: `proposal()` kendi tahminini aynı fonksiyondan
        # üretiyor ve önce yamalanırsa yükü boş çıkardı.
        row = proposal()
        mocker.patch.object(market_service, "account", return_value=account())
        mocker.patch.object(ai_service, "reprice_estimate", return_value=None)
        with pytest.raises(service.SettlementError):
            matching.fill(FakeDB(), row, 280.0)


class TestReprice:
    def test_an_order_with_nothing_to_price_yields_no_estimate(self):
        """Adet de tutar da yoksa sıfırlanmış bir tahmin döndürmek, bedava
        bir işlem gibi görünürdü."""
        assert ai_service.reprice_estimate(
            {"currency": "TRY", "fx": None}, "BUY", None, 280.0
        ) is None


class TestRunMatching:
    def _patch_market(self, mocker, quotes=None, trading=None):
        mocker.patch.object(market_service, "latest_quotes", return_value=quotes or {})
        mocker.patch.object(market_service, "open_markets", return_value=trading)

    def test_nothing_waiting_is_a_complete_answer(self, mocker):
        result = matching.run_matching(FakeDB())
        assert result == {
            "scanned": 0, "filled": 0, "skipped": 0, "failed": 0, "filled_ids": [],
        }

    def test_a_matching_stock_order_is_filled(self, mocker):
        row = proposal()
        db = FakeDB(
            waiting=[row],
            products=[SimpleNamespace(symbol="THYAO", market="BIST", product_type="stock")],
        )
        self._patch_market(
            mocker,
            quotes={"THYAO": {"price": 285.0, "received_at": NOW}},
            trading={"BIST"},
        )
        fill = mocker.patch.object(matching, "fill")

        result = matching.run_matching(db)
        fill.assert_called_once_with(db, row, 285.0)
        assert result["filled"] == 1
        assert result["filled_ids"] == ["PROP-1"]
        assert db.commits == 1

    def test_a_price_above_the_limit_is_skipped(self, mocker):
        db = FakeDB(
            waiting=[proposal()],
            products=[SimpleNamespace(symbol="THYAO", market="BIST", product_type="stock")],
        )
        self._patch_market(
            mocker,
            quotes={"THYAO": {"price": 305.0, "received_at": NOW}},
            trading={"BIST"},
        )
        assert matching.run_matching(db)["skipped"] == 1

    def test_a_fund_order_is_priced_from_its_nav(self, mocker):
        """Fonun gün içi fiyatı yok; `market_quotes` yerine günlük NAV
        okunuyor."""
        row = proposal(symbol="AFA", limit_price=13.0)
        db = FakeDB(
            waiting=[row],
            products=[SimpleNamespace(symbol="AFA", market="TEFAS", product_type="fund")],
            funds=[SimpleNamespace(code="AFA", price=12.5, as_of=TODAY)],
        )
        self._patch_market(mocker, quotes={}, trading=set())
        fill = mocker.patch.object(matching, "fill")

        assert matching.run_matching(db)["filled"] == 1
        fill.assert_called_once_with(db, row, 12.5)

    def test_an_unknown_instrument_is_skipped(self, mocker):
        db = FakeDB(waiting=[proposal()], products=[])
        self._patch_market(mocker)
        assert matching.run_matching(db)["skipped"] == 1

    def test_an_order_without_a_trigger_is_skipped(self, mocker):
        """Limit fiyatı olmayan bir satır `WAITING_PRICE`ta olmamalı; olursa
        neye göre doldurulacağı tanımsız."""
        db = FakeDB(
            waiting=[proposal(limit_price=None)],
            products=[SimpleNamespace(symbol="THYAO", market="BIST", product_type="stock")],
        )
        self._patch_market(mocker)
        assert matching.run_matching(db)["skipped"] == 1

    def test_one_failing_order_does_not_stop_the_others(self, mocker, caplog):
        rows = [proposal(id="PROP-1"), proposal(id="PROP-2")]
        db = FakeDB(
            waiting=rows,
            products=[SimpleNamespace(symbol="THYAO", market="BIST", product_type="stock")],
        )
        self._patch_market(
            mocker,
            quotes={"THYAO": {"price": 285.0, "received_at": NOW}},
            trading={"BIST"},
        )
        mocker.patch.object(
            matching, "fill",
            side_effect=[service.SettlementError("bakiye yetersiz"), None],
        )
        with caplog.at_level("ERROR"):
            result = matching.run_matching(db)
        assert result == {
            "scanned": 2, "filled": 1, "skipped": 0, "failed": 1,
            "filled_ids": ["PROP-2"],
        }
        assert db.rollbacks == 1
        assert "bakiye yetersiz" in caplog.text


class TestSweepStalePending:
    def test_nothing_pending_releases_nothing(self):
        assert matching.sweep_stale_pending(FakeDB()) == 0

    def test_a_stranded_row_is_released_and_reported(self, mocker):
        """Süreç ölürken bloke kalmış para geri veriliyor; kullanıcı
        bakiyesinin neden eksildiğini açıklayamazdı."""
        row = proposal(status="PENDING", created_at=NOW - timedelta(hours=2))
        db = FakeDB(pending=[row])
        mocker.patch.object(market_service, "account", return_value=account())
        rollback = mocker.patch.object(service, "rollback_funds")

        assert matching.sweep_stale_pending(db) == 1
        rollback.assert_called_once()
        assert row.status == "FAILED"
        assert any("Tamamlanamadı" in getattr(o, "title", "") for o in db.added)

    def test_a_row_without_an_account_is_left_alone(self, mocker):
        """Hesabı bulunamayan bir satırda "iade ettik" demek, etmeden
        söylemek olurdu."""
        row = proposal(status="PENDING")
        db = FakeDB(pending=[row])
        mocker.patch.object(market_service, "account", return_value=None)
        assert matching.sweep_stale_pending(db) == 0
        assert row.status == "PENDING"

    def test_a_failing_release_is_logged_and_rolled_back(self, mocker, caplog):
        db = FakeDB(pending=[proposal(status="PENDING")])
        mocker.patch.object(market_service, "account", return_value=account())
        mocker.patch.object(
            service, "rollback_funds", side_effect=service.SettlementError("olmadı")
        )
        with caplog.at_level("ERROR"):
            assert matching.sweep_stale_pending(db) == 0
        assert db.rollbacks == 1
        assert "olmadı" in caplog.text


class TestJob:
    @pytest.mark.asyncio
    async def test_the_job_runs_both_passes_and_mails_the_fills(self, mocker, caplog):
        db = MagicMock()
        session = MagicMock()
        session.__enter__ = MagicMock(return_value=db)
        session.__exit__ = MagicMock(return_value=False)
        mocker.patch("app.core.database.SessionLocal", return_value=session)
        mocker.patch.object(
            matching, "run_matching",
            return_value={"scanned": 1, "filled": 1, "skipped": 0, "failed": 0,
                          "filled_ids": ["PROP-1"]},
        )
        mocker.patch.object(matching, "sweep_stale_pending", return_value=2)
        mail = mocker.patch.object(matching, "_send_fill_email")

        with caplog.at_level("INFO"):
            await matching.match_open_orders_job()

        mail.assert_awaited_once_with(db, "PROP-1")
        assert "'released': 2" in caplog.text


class TestFillEmail:
    def _user(self, email="a@b.test", prefs=None):
        return SimpleNamespace(
            email=email,
            notification_preferences=prefs if prefs is not None else {},
        )

    @pytest.mark.asyncio
    async def test_a_filled_order_is_mailed(self, mocker):
        db = MagicMock()
        row = proposal(confirmed_at=NOW)
        db.get.side_effect = [row, self._user()]
        send = mocker.patch("app.core.email.send_transaction_email")

        await matching._send_fill_email(db, "PROP-1")
        kwargs = send.await_args.kwargs
        assert kwargs["asset_symbol"] == "THYAO"
        # Birim fiyat toplamdan türetiliyor: masraflar dahil olduğu için
        # limitin biraz üstünde, ve tam olarak toplam/adet.
        assert kwargs["price"] == pytest.approx(kwargs["total_amount"] / 10.0)
        assert kwargs["price"] > 290.0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("rows", [
        [None],
        [proposal(), None],
        [proposal(), SimpleNamespace(email="", notification_preferences={})],
        [proposal(), SimpleNamespace(
            email="a@b.test",
            notification_preferences={"transactions": {"email": False}},
        )],
    ])
    async def test_nothing_is_sent_when_there_is_no_addressee(self, mocker, rows):
        db = MagicMock()
        db.get.side_effect = rows
        send = mocker.patch("app.core.email.send_transaction_email")
        await matching._send_fill_email(db, "PROP-1")
        send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_mail_failure_does_not_unwind_a_committed_fill(self, mocker, caplog):
        """Bir posta sunucusu arızası, gerçekleşmiş ve commit edilmiş bir
        emri geri almaz."""
        db = MagicMock()
        db.get.side_effect = [proposal(confirmed_at=NOW), self._user()]
        mocker.patch(
            "app.core.email.send_transaction_email", side_effect=RuntimeError("smtp")
        )
        with caplog.at_level("ERROR"):
            await matching._send_fill_email(db, "PROP-1")
        assert "smtp" in caplog.text


class TestZeroQuantityEmail:
    @pytest.mark.asyncio
    async def test_a_zero_quantity_does_not_divide_by_zero(self, mocker):
        db = MagicMock()
        db.get.side_effect = [
            proposal(quantity=0, confirmed_at=NOW),
            SimpleNamespace(email="a@b.test", notification_preferences={}),
        ]
        send = mocker.patch("app.core.email.send_transaction_email")
        await matching._send_fill_email(db, "PROP-1")
        assert send.await_args.kwargs["price"] == 0.0
