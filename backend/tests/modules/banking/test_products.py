"""Cards and loans.

These two screens rendered `MOCK_BANKING_DATA` until now: a limit nobody set,
a debt nobody owed and a pay button that edited React state.

The rule running through this module is that DERIVED values are computed at
read time. A stored `available_limit` can disagree with its own limit and debt
the moment either moves, which is the same reason `portfolio_positions` does
not store market value.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.modules.banking import products


def _card(limit=50000.0, debt=8450.75, **over):
    base = dict(
        id="c-1", user_id="u-1", name="Platinum", brand="mastercard",
        card_number="5287 **** **** 8024", credit_limit=limit, current_debt=debt,
        due_day=12, color=None, is_digital=False, settings={},
        linked_account_id=None, status="active",
    )
    base.update(over)
    return SimpleNamespace(**base)


def _loan(principal=60000.0, remaining=60000.0, paid=0, **over):
    base = dict(
        id="l-1", user_id="u-1", title="İhtiyaç Kredisi", principal=principal,
        remaining_amount=remaining, installment_amount=5000.0,
        installment_count=12, paid_installments=paid,
        next_due=date.today() + timedelta(days=30), status="active",
    )
    base.update(over)
    return SimpleNamespace(**base)


def _db(*rows):
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = list(rows)
    db.query.return_value.filter.return_value.first.return_value = rows[0] if rows else None
    return db


class TestDerivedValues:
    def test_available_limit_is_computed_not_stored(self):
        rows = products.cards_for(_db(_card(50000, 8450.75)), "u-1")
        assert rows[0]["available_limit"] == 41549.25

    def test_a_maxed_card_has_nothing_available(self):
        rows = products.cards_for(_db(_card(1000, 1000)), "u-1")
        assert rows[0]["available_limit"] == 0

    def test_loan_progress_comes_from_what_is_paid(self):
        rows = products.loans_for(_db(_loan(60000, 55000)), "u-1")
        assert rows[0]["progress_percentage"] == pytest.approx(8.3, abs=0.1)

    def test_remaining_months_never_goes_negative(self):
        """An over-counted instalment should read as finished, not as a
        negative number of months."""
        rows = products.loans_for(_db(_loan(paid=99)), "u-1")
        assert rows[0]["remaining_months"] == 0

    def test_a_zero_principal_loan_reports_no_progress_rather_than_dividing(self):
        rows = products.loans_for(_db(_loan(principal=0, remaining=0)), "u-1")
        assert rows[0]["progress_percentage"] == 0.0


class TestIssuing:
    def test_a_card_gets_a_masked_number(self):
        """There is no PAN here to protect, but a stored value that looks like
        one should still look masked."""
        card = products.issue_card(
            MagicMock(spec=Session), user_id="u-1", name="Platinum",
            brand="mastercard", credit_limit=50000,
        )
        assert "****" in card.card_number and card.card_number.startswith("5")

    def test_a_visa_is_numbered_differently(self):
        card = products.issue_card(
            MagicMock(spec=Session), user_id="u-1", name="Classic",
            brand="visa", credit_limit=10000,
        )
        assert card.card_number.startswith("4")

    @pytest.mark.parametrize("limit,debt", [(0, 0), (-1, 0)])
    def test_a_nonsense_limit_is_refused(self, limit, debt):
        with pytest.raises(products.ProductError):
            products.issue_card(
                MagicMock(spec=Session), user_id="u-1", name="X",
                brand="visa", credit_limit=limit, current_debt=debt,
            )

    def test_debt_above_the_limit_is_refused(self):
        with pytest.raises(products.ProductError, match="limit"):
            products.issue_card(
                MagicMock(spec=Session), user_id="u-1", name="X", brand="visa",
                credit_limit=1000, current_debt=5000,
            )

    def test_a_loan_defaults_to_equal_instalments(self):
        loan = products.issue_loan(
            MagicMock(spec=Session), user_id="u-1", title="K",
            principal=60000, installment_count=12,
        )
        assert loan.installment_amount == 5000.0
        assert loan.remaining_amount == 60000.0

    def test_an_explicit_instalment_wins(self):
        loan = products.issue_loan(
            MagicMock(spec=Session), user_id="u-1", title="K",
            principal=60000, installment_count=12, installment_amount=6000,
        )
        assert loan.installment_amount == 6000

    @pytest.mark.parametrize("principal,count", [(0, 12), (1000, 0)])
    def test_nonsense_loan_terms_are_refused(self, principal, count):
        with pytest.raises(products.ProductError):
            products.issue_loan(
                MagicMock(spec=Session), user_id="u-1", title="K",
                principal=principal, installment_count=count,
            )


class TestPayingThem:
    def test_a_card_payment_reduces_the_debt(self):
        card = _card(debt=8450.75)
        assert products.apply_card_payment(_db(card), "u-1", "c-1", 3000) == 5450.75

    def test_overpaying_a_card_is_refused(self):
        """A negative debt reads as the bank owing the customer money."""
        with pytest.raises(products.ProductError, match="fazlası ödenemez"):
            products.apply_card_payment(_db(_card(debt=100)), "u-1", "c-1", 500)

    def test_paying_an_unknown_card_is_refused(self):
        with pytest.raises(products.ProductError, match="Kart bulunamadı"):
            products.apply_card_payment(_db(), "u-1", "ghost", 10)

    def test_an_instalment_reduces_the_balance_and_counts(self):
        loan = _loan(remaining=60000.0)
        assert products.apply_loan_payment(_db(loan), "u-1", "l-1", 5000) == 55000.0
        assert loan.paid_installments == 1

    def test_the_next_due_date_moves_on(self):
        loan = _loan()
        before = loan.next_due
        products.apply_loan_payment(_db(loan), "u-1", "l-1", 5000)
        assert loan.next_due == before + timedelta(days=30)

    def test_a_fully_paid_loan_closes_and_stops_being_due(self):
        loan = _loan(remaining=5000.0)
        products.apply_loan_payment(_db(loan), "u-1", "l-1", 5000)
        assert loan.status == "closed" and loan.next_due is None

    def test_overpaying_a_loan_is_refused(self):
        with pytest.raises(products.ProductError, match="fazlası ödenemez"):
            products.apply_loan_payment(_db(_loan(remaining=100)), "u-1", "l-1", 500)

    def test_paying_an_unknown_loan_is_refused(self):
        with pytest.raises(products.ProductError, match="Kredi bulunamadı"):
            products.apply_loan_payment(_db(), "u-1", "ghost", 10)


class TestCardAdministration:
    def test_settings_are_merged_not_replaced(self):
        """A screen that toggles one switch must not clear the others."""
        card = _card(settings={"frozen": False, "contactless": True})
        products.update_card_settings(_db(card), "u-1", "c-1", {"frozen": True})
        assert card.settings == {"frozen": True, "contactless": True}

    def test_settings_on_an_unknown_card_are_refused(self):
        with pytest.raises(products.ProductError):
            products.update_card_settings(_db(), "u-1", "ghost", {})

    def test_a_card_with_no_debt_can_be_closed(self):
        assert products.close_card(_db(_card(debt=0)), "u-1", "c-1") is True

    def test_a_card_with_debt_cannot_be_closed(self):
        with pytest.raises(products.ProductError, match="Borcu olan"):
            products.close_card(_db(_card(debt=500)), "u-1", "c-1")

    def test_closing_an_unknown_card_reports_not_found(self):
        assert products.close_card(_db(), "u-1", "ghost") is False

    def test_a_partly_paid_loan_with_no_due_date_still_settles(self):
        """`next_due` is null once a loan closes; a later payment must not
        try to advance a date that is not there."""
        loan = _loan(remaining=10000.0, next_due=None)
        assert products.apply_loan_payment(_db(loan), "u-1", "l-1", 5000) == 5000.0
        assert loan.next_due is None
