"""Applying a confirmed trade to cash and holdings.

Confirming used to set two columns and commit — no cash moved, no position
changed — while the order list displayed "Gerçekleşti". These tests pin down
the arithmetic that makes that word true, and the refusals that keep it from
being true by accident.
"""

from __future__ import annotations

from types import SimpleNamespace
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.modules.investment import service
from app.modules.investment.models import CashMovement, PortfolioPosition


def proposal(
    transaction_type="BUY",
    symbol="THYAO",
    quantity=10,
    net_amount=3022.26,
    reference_price=301.75,
    currency="TRY",
    fx=None,
):
    estimate = {"currency": currency}
    if net_amount is not None:
        estimate["net_amount"] = net_amount
    if reference_price is not None:
        estimate["reference_price"] = reference_price
    if fx is not None:
        estimate["fx"] = fx
    return SimpleNamespace(
        id="PROP-1",
        transaction_type=transaction_type,
        symbol=symbol,
        quantity=quantity,
        payload={"estimate": estimate} if estimate else {},
    )


def account(cash=25000.0, currency="TRY"):
    return SimpleNamespace(id="acct-1", cash_balance=cash, currency_code=currency)


#: A USD proposal carrying the rate it was staged at, as _estimate now records.
USD_FX = {"rate": 47.9479, "from_currency": "USD", "to_currency": "TRY"}


class Fixture:
    """A Session double resolving one product and (optionally) one position."""

    def __init__(self, position=None, product=SimpleNamespace(id="prod-1", symbol="THYAO")):
        self.db = MagicMock(spec=Session)
        self.deleted = []
        self.added = []
        chain = self.db.query.return_value.filter.return_value
        # First lookup is the product, second is the position.
        chain.first.side_effect = [product, position]
        self.db.delete.side_effect = self.deleted.append
        self.db.add.side_effect = self.added.append


class TestBuy:
    def test_cash_falls_by_the_net_amount(self):
        """The net includes commission and BSMV, because those leave the
        account too."""
        acct = account(25000.0)
        service.settle(Fixture().db, proposal(net_amount=3022.26), acct)
        assert float(acct.cash_balance) == pytest.approx(21977.74)

    def test_a_new_holding_is_created(self):
        fix = Fixture(position=None)
        service.settle(fix.db, proposal(quantity=10), account())
        positions = [row for row in fix.added if isinstance(row, PortfolioPosition)]
        assert len(positions) == 1
        assert float(positions[0].quantity) == 10

    def test_the_cash_movement_is_recorded(self):
        """Takas artık nakit defterine de yazar.

        Yazmadığı sürece yatırım hesabının gösterebileceği bir hareket dökümü
        yoktu: bakiye değişiyor, değişikliği anlatan hiçbir satır kalmıyordu.
        """
        fix = Fixture(position=None)
        service.settle(fix.db, proposal(quantity=10, net_amount=3022.26), account(25000.0))
        movements = [row for row in fix.added if isinstance(row, CashMovement)]
        assert len(movements) == 1
        assert movements[0].direction == "DEBIT"
        assert float(movements[0].amount) == pytest.approx(3022.26)
        assert float(movements[0].balance_before) == pytest.approx(25000.0)
        assert float(movements[0].balance_after) == pytest.approx(21977.74)

    def test_the_cost_basis_is_the_reference_price_not_the_all_in_net(self):
        """Fees are an expense, not part of what the shares are worth. Folding
        them into the basis would overstate the break-even price."""
        fix = Fixture(position=None)
        service.settle(fix.db, proposal(quantity=10, net_amount=3022.26, reference_price=301.75), account())
        assert float(fix.added[0].average_buy_price) == pytest.approx(301.75)

    def test_adding_to_a_holding_uses_a_weighted_average(self):
        """The old basis keeps its weight in the shares it applies to.
        Overwriting with the latest price would erase what the position cost."""
        position = SimpleNamespace(quantity=100.0, average_buy_price=200.0, updated_at=None)
        fix = Fixture(position=position)
        service.settle(fix.db, proposal(quantity=100, reference_price=300.0), account(100000.0))
        # 100 @ 200 plus 100 @ 300 -> 200 @ 250
        assert float(position.quantity) == 200
        assert float(position.average_buy_price) == pytest.approx(250.0)

    def test_a_purchase_over_the_balance_is_refused(self):
        acct = account(1000.0)
        with pytest.raises(service.SettlementError) as excinfo:
            service.settle(Fixture().db, proposal(net_amount=3022.26), acct)
        assert "yetersiz" in str(excinfo.value).lower()
        assert float(acct.cash_balance) == 1000.0, "a refused trade must not move cash"

    def test_spending_the_balance_exactly_is_allowed(self):
        acct = account(3022.26)
        service.settle(Fixture().db, proposal(net_amount=3022.26), acct)
        assert float(acct.cash_balance) == pytest.approx(0.0)


class TestSell:
    def test_cash_rises_by_the_net_amount(self):
        position = SimpleNamespace(quantity=100.0, average_buy_price=200.0, updated_at=None)
        acct = account(5000.0)
        service.settle(
            Fixture(position=position).db,
            proposal(transaction_type="SELL", quantity=10, net_amount=2990.0),
            acct,
        )
        assert float(acct.cash_balance) == pytest.approx(7990.0)

    def test_the_holding_shrinks(self):
        position = SimpleNamespace(quantity=100.0, average_buy_price=200.0, updated_at=None)
        service.settle(
            Fixture(position=position).db,
            proposal(transaction_type="SELL", quantity=30),
            account(),
        )
        assert float(position.quantity) == 70

    def test_selling_does_not_change_the_average_cost(self):
        """A sale does not alter what the remaining shares cost to acquire."""
        position = SimpleNamespace(quantity=100.0, average_buy_price=200.0, updated_at=None)
        service.settle(
            Fixture(position=position).db,
            proposal(transaction_type="SELL", quantity=30),
            account(),
        )
        assert float(position.average_buy_price) == 200.0

    def test_selling_everything_removes_the_row(self):
        """Average cost is meaningless without shares; a zero-quantity row
        would linger in the portfolio as a holding of nothing."""
        position = SimpleNamespace(quantity=50.0, average_buy_price=200.0, updated_at=None)
        fix = Fixture(position=position)
        service.settle(fix.db, proposal(transaction_type="SELL", quantity=50), account())
        assert fix.deleted == [position]

    def test_float_dust_still_closes_the_position(self):
        """A full sell can leave 1e-15 behind. A row claiming a billionth of a
        share is noise pretending to be a holding."""
        position = SimpleNamespace(quantity=50.0 + 1e-12, average_buy_price=200.0, updated_at=None)
        fix = Fixture(position=position)
        service.settle(fix.db, proposal(transaction_type="SELL", quantity=50), account())
        assert fix.deleted == [position]

    def test_selling_more_than_held_is_refused(self):
        position = SimpleNamespace(quantity=5.0, average_buy_price=200.0, updated_at=None)
        acct = account(1000.0)
        with pytest.raises(service.SettlementError):
            service.settle(
                Fixture(position=position).db,
                proposal(transaction_type="SELL", quantity=50),
                acct,
            )
        assert float(acct.cash_balance) == 1000.0

    def test_selling_something_not_held_is_refused(self):
        with pytest.raises(service.SettlementError):
            service.settle(
                Fixture(position=None).db,
                proposal(transaction_type="SELL", quantity=1),
                account(),
            )


class TestRefusals:
    def test_a_proposal_without_an_amount_is_not_settled(self):
        """Re-pricing here would settle at a figure the user never approved."""
        acct = account()
        with pytest.raises(service.SettlementError):
            service.settle(Fixture().db, proposal(net_amount=None, reference_price=None), acct)
        assert float(acct.cash_balance) == 25000.0

    def test_a_transfer_has_no_settlement_path(self):
        """Banking does not exist. Pretending a transfer settled would be the
        same lie in a new place."""
        with pytest.raises(service.SettlementError) as excinfo:
            service.settle(Fixture().db, proposal(transaction_type="TRANSFER"), account())
        assert "takas" in str(excinfo.value).lower()

    def test_an_unknown_instrument_is_refused(self):
        fix = Fixture(product=None)
        with pytest.raises(service.SettlementError):
            service.settle(fix.db, proposal(), account())

    def test_nothing_is_committed_by_the_service(self):
        """The caller commits once, together with the status flip, so a crash
        cannot move money and leave the proposal pending."""
        fix = Fixture()
        service.settle(fix.db, proposal(), account())
        assert not fix.db.commit.called


class TestPriceFallback:
    def test_a_missing_reference_price_falls_back_to_the_net_per_share(self):
        """Better than booking a zero basis, which would report the whole
        position as pure profit."""
        fix = Fixture(position=None)
        service.settle(fix.db, proposal(quantity=10, net_amount=3000.0, reference_price=None), account())
        assert float(fix.added[0].average_buy_price) == pytest.approx(300.0)

    def test_a_zero_quantity_does_not_divide_by_zero(self):
        fix = Fixture(position=None)
        service.settle(fix.db, proposal(quantity=0, net_amount=0.0, reference_price=None), account())
        assert float(fix.added[0].average_buy_price) == 0.0


class TestEnsureAccount:
    def test_an_existing_account_is_reused(self):
        """Registration is not the only caller; opening a second account for
        the same user would split their cash in two."""
        db = MagicMock(spec=Session)
        existing = SimpleNamespace(id="acct-1", user_id="user-1")
        db.query.return_value.filter.return_value.first.return_value = existing
        assert service.ensure_account(db, "user-1") is existing
        assert not db.add.called

    def test_a_new_account_opens_with_starting_cash(self):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = None
        account = service.ensure_account(db, "user-2")
        assert account.user_id == "user-2"
        assert float(account.cash_balance) == service.STARTING_CASH
        assert db.add.called

    def test_the_account_number_derives_from_the_user_id(self):
        """Derived rather than counted: two concurrent registrations cannot
        collide on a shared counter."""
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = None
        first = service.ensure_account(db, "aaaaaaaa-1111-2222-3333-444444444444")
        second = service.ensure_account(db, "bbbbbbbb-1111-2222-3333-444444444444")
        assert first.account_number != second.account_number


class TestForeignCurrency:
    """The instrument's currency and the account's are different things.

    AAPL is priced in USD; the account holds TRY. Applying `net_amount`
    straight to `cash_balance` debited 315 TL for a 15.098 TL purchase and
    credited 4.723 TL for a 226.468 TL sale — destroying 97% of the position's
    value on the way out.
    """

    def test_a_usd_buy_debits_the_converted_amount(self):
        acct = account(500_000.0)
        service.settle(
            Fixture().db,
            proposal(quantity=1, net_amount=315.0, reference_price=314.88,
                     currency="USD", fx=USD_FX),
            acct,
        )
        spent = 500_000.0 - float(acct.cash_balance)
        assert spent == pytest.approx(315.0 * 47.9479, rel=1e-6)
        assert spent > 15_000, "a 15.000 TL purchase must not cost 315 TL"

    def test_a_usd_sell_credits_the_converted_amount(self):
        """The direction that lost the most money."""
        position = SimpleNamespace(quantity=15.0, average_buy_price=264.0, updated_at=None)
        acct = account(1000.0)
        service.settle(
            Fixture(position=position).db,
            proposal(transaction_type="SELL", quantity=15, net_amount=4723.0,
                     currency="USD", fx=USD_FX),
            acct,
        )
        gained = float(acct.cash_balance) - 1000.0
        assert gained == pytest.approx(4723.0 * 47.9479, rel=1e-6)
        assert gained > 200_000

    def test_a_try_trade_is_not_converted(self):
        acct = account(25000.0)
        service.settle(Fixture().db, proposal(net_amount=3022.26), acct)
        assert float(acct.cash_balance) == pytest.approx(25000.0 - 3022.26)

    def test_a_foreign_trade_without_its_rate_is_refused(self):
        """Settling at 1.0 is what caused the loss. Refusing costs a retry."""
        acct = account(500_000.0)
        with pytest.raises(service.SettlementError) as excinfo:
            service.settle(
                Fixture().db,
                proposal(quantity=1, net_amount=315.0, currency="USD", fx=None),
                acct,
            )
        assert "kur" in str(excinfo.value).lower()
        assert float(acct.cash_balance) == 500_000.0

    def test_a_mismatched_rate_is_refused_rather_than_applied(self):
        """An fx block naming a different currency pair cannot be trusted to
        describe this trade."""
        acct = account(500_000.0)
        wrong = {"rate": 47.9, "from_currency": "EUR", "to_currency": "TRY"}
        with pytest.raises(service.SettlementError):
            service.settle(
                Fixture().db,
                proposal(quantity=1, net_amount=315.0, currency="USD", fx=wrong),
                acct,
            )

    def test_the_cost_basis_stays_in_the_instruments_currency(self):
        """`average_buy_price` sits beside a USD price feed and is converted at
        read time; converting here too would double-convert the P&L."""
        fix = Fixture(position=None)
        service.settle(
            fix.db,
            proposal(quantity=1, net_amount=315.0, reference_price=314.88,
                     currency="USD", fx=USD_FX),
            account(500_000.0),
        )
        assert float(fix.added[0].average_buy_price) == pytest.approx(314.88)

    def test_the_insufficient_funds_message_names_the_account_currency(self):
        acct = account(100.0)
        with pytest.raises(service.SettlementError) as excinfo:
            service.settle(
                Fixture().db,
                proposal(quantity=1, net_amount=315.0, currency="USD", fx=USD_FX),
                acct,
            )
        assert "TRY" in str(excinfo.value)


class TestCashStatement:
    """Döküm defterden okunur, bakiyeden yeniden oynatılarak üretilmez.

    Bakiyeyi üç ayrı yer yazıyor ve biri -- yöneticinin düzeltmesi -- hiçbir
    zaman bir işleme bağlanmıyor; geriye doğru hesap bu yüzden sessizce
    kayardı.
    """

    def _account(self):
        return SimpleNamespace(
            id="ia-1", account_number="TR-INV", iban="TR00INV",
            currency_code="TRY", cash_balance=1500.0,
        )

    def _db(self, rows):
        db = MagicMock(spec=Session)
        chain = db.query.return_value.filter.return_value.order_by.return_value
        chain.limit.return_value.all.return_value = rows
        return db

    def test_rows_are_projected_onto_the_banking_shape(self):
        """Bankacılık dökümüyle aynı alanlar; arayüz iki listeyi de aynı satır
        bileşeniyle basabilsin."""
        row = SimpleNamespace(
            reference="PRP-1", direction="DEBIT", amount=500.0,
            balance_after=1500.0, description="Alım — THYAO x2",
            created_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
        )
        out = service.cash_statement(self._db([row]), self._account())
        assert out["iban"] == "TR00INV"
        assert out["balance"] == 1500.0
        movement = out["movements"][0]
        assert movement["reference_number"] == "PRP-1"
        assert movement["direction"] == "DEBIT"
        assert movement["balance_after"] == 1500.0
        # Bir alımın karşısında IBAN yoktur; açıklama zaten enstrümanı söylüyor.
        assert movement["counterparty_iban"] is None

    def test_an_account_without_a_stored_iban_still_reports_one(self):
        account = self._account()
        account.iban = None
        out = service.cash_statement(self._db([]), account)
        assert out["iban"] == service.iban_for("TR-INV")

    def test_no_movements_is_an_empty_list_not_an_error(self):
        """Hiç hareketi olmayan hesap boş görünür; hata değildir."""
        assert service.cash_statement(self._db([]), self._account())["movements"] == []


class TestRecordCashMovement:
    def test_direction_is_read_from_the_sign_not_supplied(self):
        """Yön tutardan değil, bakiyenin gidiş yönünden okunur -- iki ayrı
        alan tutmak, ikisinin çelişebileceği bir durum yaratırdı."""
        db = MagicMock(spec=Session)
        account = SimpleNamespace(id="ia-1")
        credit = service.record_cash_movement(
            db, account, amount=100.0, balance_before=0.0, balance_after=100.0,
            description="giriş",
        )
        debit = service.record_cash_movement(
            db, account, amount=-40.0, balance_before=100.0, balance_after=60.0,
            description="çıkış",
        )
        assert credit.direction == "CREDIT" and float(credit.amount) == 100.0
        assert debit.direction == "DEBIT" and float(debit.amount) == 40.0

    def test_a_long_description_is_trimmed_to_the_column(self):
        """Sütun 255; kırpmamak kaydın tamamını düşürürdü."""
        movement = service.record_cash_movement(
            MagicMock(spec=Session), SimpleNamespace(id="ia-1"),
            amount=1.0, balance_before=0.0, balance_after=1.0,
            description="x" * 400,
        )
        assert len(movement.description) == 255


# --------------------------------------------------------------------------
# İki fazlı takas: blokaj, sonra dolum ya da iade.
#
# Bu üçlü `settle`den ayrı bir yol ve HİÇ testi yoktu. Emir akışı onun
# üzerine kuruluyor: onay parayı bloke ediyor, eşleştirici günler sonra
# dolduruyor ya da iptal iade ediyor. Aradaki her adım ölçülmediği sürece
# "bloke" ile "kayıp" birbirinden ayırt edilemez.
# --------------------------------------------------------------------------
class TestBlockFunds:
    def test_a_buy_takes_the_cash_out_immediately(self):
        """Çift harcamayı önleyen şey bu: aynı bakiyeye karşı iki emir
        verilip ikisi de beklemeye alınabiliyor."""
        fixture = Fixture()
        owner = account(cash=25000.0)
        applied = service.block_funds(fixture.db, proposal(), owner)

        assert owner.cash_balance == pytest.approx(25000.0 - 3022.26)
        assert applied["cash_delta"] == pytest.approx(-3022.26)
        movement = next(m for m in fixture.added if isinstance(m, CashMovement))
        assert movement.direction == "DEBIT"
        assert "Blokesi" in movement.description

    def test_a_buy_beyond_the_balance_is_refused_with_both_figures(self):
        fixture = Fixture()
        with pytest.raises(service.SettlementError) as excinfo:
            service.block_funds(fixture.db, proposal(), account(cash=100.0))
        assert "3.022,26" in str(excinfo.value).replace(",", "X").replace(".", ",").replace("X", ".")

    def test_a_sell_takes_the_shares_out_not_the_cash(self):
        """Çift satışı önleyen şey bu. Nakit HAREKET ETMİYOR: satışın parası
        dolumda geliyor."""
        position = SimpleNamespace(quantity=30.0, updated_at=None)
        fixture = Fixture(position=position)
        owner = account()
        applied = service.block_funds(
            fixture.db, proposal(transaction_type="SELL"), owner
        )
        assert position.quantity == pytest.approx(20.0)
        assert applied["cash_delta"] == 0.0
        assert owner.cash_balance == 25000.0

    def test_selling_the_whole_position_removes_the_row(self):
        """Sıfır adetlik bir satır, portföyde artık tutulmayan bir hisseyi
        tutuluyormuş gibi gösterirdi."""
        fixture = Fixture(position=SimpleNamespace(quantity=10.0, updated_at=None))
        service.block_funds(fixture.db, proposal(transaction_type="SELL"), account())
        assert len(fixture.deleted) == 1

    def test_selling_more_than_is_held_is_refused(self):
        fixture = Fixture(position=SimpleNamespace(quantity=3.0, updated_at=None))
        with pytest.raises(service.SettlementError):
            service.block_funds(fixture.db, proposal(transaction_type="SELL"), account())

    def test_selling_with_no_position_at_all_is_refused(self):
        fixture = Fixture(position=None)
        with pytest.raises(service.SettlementError):
            service.block_funds(fixture.db, proposal(transaction_type="SELL"), account())

    def test_a_proposal_without_an_amount_is_refused(self):
        """Sıfırlanmış bir tutarla bloke etmek, bedava bir emir olurdu."""
        fixture = Fixture()
        with pytest.raises(service.SettlementError):
            service.block_funds(fixture.db, proposal(net_amount=None), account())

    def test_an_unknown_direction_has_no_blocking_step(self):
        fixture = Fixture()
        with pytest.raises(service.SettlementError):
            service.block_funds(
                fixture.db, proposal(transaction_type="TRANSFER"), account()
            )


class TestFinalizeSettlement:
    def test_a_buy_delivers_the_shares_without_touching_cash_again(self):
        """Nakit blokajda çıktı. İkinci kez düşmek, aynı alımı iki kez
        ödetirdi."""
        fixture = Fixture(position=None)
        owner = account(cash=21977.74)
        service.finalize_settlement(fixture.db, proposal(), owner)

        position = next(p for p in fixture.added if isinstance(p, PortfolioPosition))
        assert float(position.quantity) == pytest.approx(10.0)
        assert float(position.average_buy_price) == pytest.approx(301.75)
        assert owner.cash_balance == 21977.74

    def test_a_second_buy_averages_the_cost(self):
        position = SimpleNamespace(
            quantity=10.0, average_buy_price=200.0, updated_at=None
        )
        fixture = Fixture(position=position)
        service.finalize_settlement(fixture.db, proposal(), account())
        assert float(position.quantity) == pytest.approx(20.0)
        assert float(position.average_buy_price) == pytest.approx((200.0 + 301.75) / 2)

    def test_a_sell_pays_the_cash_the_blocked_shares_were_worth(self):
        fixture = Fixture()
        owner = account(cash=25000.0)
        applied = service.finalize_settlement(
            fixture.db, proposal(transaction_type="SELL"), owner
        )
        assert owner.cash_balance == pytest.approx(25000.0 + 3022.26)
        assert applied["cash_delta"] == pytest.approx(3022.26)

    def test_an_unknown_direction_is_refused(self):
        fixture = Fixture()
        with pytest.raises(service.SettlementError):
            service.finalize_settlement(
                fixture.db, proposal(transaction_type="TRANSFER"), account()
            )


class TestRollbackFunds:
    def test_a_cancelled_buy_returns_the_cash_to_the_kurus(self):
        fixture = Fixture()
        owner = account(cash=21977.74)
        service.rollback_funds(fixture.db, proposal(), owner)

        assert owner.cash_balance == pytest.approx(25000.0)
        movement = next(m for m in fixture.added if isinstance(m, CashMovement))
        assert movement.direction == "CREDIT"
        assert "İade" in movement.description

    def test_a_cancelled_sell_puts_the_shares_back_on_an_existing_row(self):
        position = SimpleNamespace(quantity=20.0, updated_at=None)
        fixture = Fixture(position=position)
        service.rollback_funds(
            fixture.db, proposal(transaction_type="SELL"), account()
        )
        assert position.quantity == pytest.approx(30.0)

    def test_a_cancelled_sell_recreates_a_row_that_was_emptied(self):
        """Blokaj pozisyonu SİLİYOR: tamamı satılan bir emrin iptalinde geri
        koyacak satır yok ve olmayan satıra eklemek hisseyi yok ederdi."""
        fixture = Fixture(position=None)
        service.rollback_funds(
            fixture.db, proposal(transaction_type="SELL"), account()
        )
        position = next(p for p in fixture.added if isinstance(p, PortfolioPosition))
        assert float(position.quantity) == pytest.approx(10.0)
        assert float(position.average_buy_price) == pytest.approx(301.75)

    def test_an_unknown_direction_moves_nothing(self):
        """Tanımadığı bir türde sessizce para iade etmek, olmayan bir
        blokajı geri vermek olurdu."""
        fixture = Fixture()
        owner = account(cash=100.0)
        service.rollback_funds(
            fixture.db, proposal(transaction_type="TRANSFER"), owner
        )
        assert owner.cash_balance == 100.0
        assert fixture.added == []
