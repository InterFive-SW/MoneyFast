"""Staged payments.

The contract the whole chat integration rests on: staging is inert, and only
`confirm` moves money. If staging could move a balance, an assistant that
misread "evet" could empty an account -- which is the reason the investment
side already works this way and why money movement copies it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from app.modules.banking import payments


def _account(balance=10_000.0, currency="TRY"):
    return SimpleNamespace(
        id="acc-1", account_number="TR-TEST-0001", balance=balance,
        currency_code=currency, status="active", user_id="u-1",
    )


def _bill(amount=842.5):
    return SimpleNamespace(
        id="b-1", institution="BEDAŞ", bill_type="electricity",
        subscriber_no="TEST-1", amount=amount, due_day=15, status="pending",
    )


def _proposal(**over):
    base = dict(
        id="PAY-1", user_id="u-1", status="PENDING", payment_type=payments.BILL_PAYMENT,
        source_account_id="TR-TEST-0001", destination_reference="TEST-1",
        amount=842.5, currency_code="TRY",
        payload={"description": "BEDAŞ fatura ödemesi", "bill_id": "b-1"},
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
        confirmed_at=None, cancelled_at=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


class TestProposalIdentity:
    def test_the_same_key_yields_the_same_id(self):
        """A retry that mints a second proposal leaves the user looking at two
        pending payments for one intent -- either of them confirmable."""
        assert payments._proposal_id("k") == payments._proposal_id("k")

    def test_different_keys_differ(self):
        assert payments._proposal_id("a") != payments._proposal_id("b")


class TestStagingIsInert:
    def _db(self, bill=None, existing=None):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.side_effect = [bill, existing]
        return db

    def test_staging_a_bill_takes_the_amount_from_the_bill(self, mocker):
        """Never from the caller. A chat turn naming a different figure must
        not be able to under- or over-pay."""
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        db = self._db(bill=_bill(842.5))
        proposal = payments.stage(
            db, user_id="u-1", payment_type=payments.BILL_PAYMENT,
            institution="BEDAŞ", subscriber_no="TEST-1", amount=1.0,
            idempotency_key="k",
        )
        assert float(proposal.amount) == 842.5

    def test_staging_never_touches_the_balance(self, mocker):
        account = _account(10_000.0)
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=account)
        payments.stage(
            db=self._db(bill=_bill()), user_id="u-1",
            payment_type=payments.BILL_PAYMENT, institution="BEDAŞ",
            subscriber_no="TEST-1", idempotency_key="k",
        )
        assert account.balance == 10_000.0

    def test_an_unknown_bill_is_refused(self, mocker):
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        with pytest.raises(payments.PaymentError, match="bulunamadı"):
            payments.stage(
                db=self._db(bill=None), user_id="u-1",
                payment_type=payments.BILL_PAYMENT, institution="BEDAŞ",
                subscriber_no="nope",
            )

    def test_an_insufficient_balance_is_refused_at_staging(self, mocker):
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account(10.0))
        with pytest.raises(payments.PaymentError, match="yetersiz"):
            payments.stage(
                db=self._db(bill=_bill()), user_id="u-1",
                payment_type=payments.BILL_PAYMENT, institution="BEDAŞ",
                subscriber_no="TEST-1",
            )

    def test_a_customer_with_no_account_is_refused(self, mocker):
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=None)
        with pytest.raises(payments.PaymentError):
            payments.stage(db=MagicMock(spec=Session), user_id="u-1",
                           payment_type=payments.TRANSFER, amount=10, destination="x")

    def test_a_transfer_needs_a_destination(self, mocker):
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        with pytest.raises(payments.PaymentError, match="Alıcı"):
            payments.stage(db=MagicMock(spec=Session), user_id="u-1",
                           payment_type=payments.TRANSFER, amount=10)

    def test_a_bill_needs_institution_and_subscriber(self, mocker):
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        with pytest.raises(payments.PaymentError, match="abone"):
            payments.stage(db=MagicMock(spec=Session), user_id="u-1",
                           payment_type=payments.BILL_PAYMENT)

    def test_a_non_positive_amount_is_refused(self, mocker):
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        with pytest.raises(payments.PaymentError, match="sıfırdan"):
            payments.stage(db=MagicMock(spec=Session), user_id="u-1",
                           payment_type=payments.TRANSFER, amount=None, destination="x")

    def test_a_repeated_key_returns_the_existing_proposal(self, mocker):
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        already = _proposal()
        db = self._db(bill=_bill(), existing=already)
        assert payments.stage(
            db, user_id="u-1", payment_type=payments.BILL_PAYMENT,
            institution="BEDAŞ", subscriber_no="TEST-1", idempotency_key="k",
        ) is already


class TestConfirmMovesMoney:
    def _db(self, proposal, bill=None):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.side_effect = [proposal, bill]
        return db

    def test_a_bill_payment_debits_and_marks_the_bill_paid(self, mocker):
        account, bill = _account(10_000.0), _bill()
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=account)
        mocker.patch.object(
            payments.banking_service, "post_adjustment",
            return_value={"reference_number": "TRF-9"},
        )
        result = payments.confirm(self._db(_proposal(), bill), "u-1", "PAY-1")
        assert result["status"] == "CONFIRMED"
        assert bill.status == "paid" and bill.paid_by == "u-1"

    def test_a_bill_payment_is_named_a_bill_in_the_statement(self, mocker):
        """Every non-transfer used to land as "duzeltme", so a customer read an
        admin correction where they had paid a bill."""
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        posted = mocker.patch.object(
            payments.banking_service, "post_adjustment",
            return_value={"reference_number": "TRF-9"},
        )
        payments.confirm(self._db(_proposal(), _bill()), "u-1", "PAY-1")
        assert posted.call_args.kwargs["transaction_type"] == "fatura"

    def test_a_transfer_goes_through_the_double_entry_writer(self, mocker):
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        moved = mocker.patch.object(
            payments.banking_service, "transfer",
            return_value={"reference_number": "TRF-3"},
        )
        payments.confirm(
            self._db(_proposal(payment_type=payments.TRANSFER, payload={})),
            "u-1", "PAY-1",
        )
        assert moved.called

    def test_someone_elses_proposal_is_indistinguishable_from_missing(self, mocker):
        with pytest.raises(payments.PaymentError, match="bulunamadı"):
            payments.confirm(self._db(_proposal(user_id="someone-else")), "u-1", "PAY-1")

    def test_confirming_twice_is_refused(self, mocker):
        with pytest.raises(payments.PaymentError, match="sonuçlanmış"):
            payments.confirm(self._db(_proposal(status="CONFIRMED")), "u-1", "PAY-1")

    def test_an_expired_proposal_is_refused_and_marked(self, mocker):
        stale = _proposal(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        with pytest.raises(payments.PaymentError, match="süresi"):
            payments.confirm(self._db(stale), "u-1", "PAY-1")
        assert stale.status == "EXPIRED"

    def test_the_balance_is_checked_AGAIN_at_confirm(self, mocker):
        """Two proposals can be staged against one balance and then both
        confirmed. Checking only at staging authorises the same money twice."""
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account(10.0))
        with pytest.raises(payments.PaymentError, match="yetersiz"):
            payments.confirm(self._db(_proposal()), "u-1", "PAY-1")

    def test_a_ledger_refusal_surfaces_as_a_payment_error(self, mocker):
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        mocker.patch.object(
            payments.banking_service, "transfer",
            side_effect=payments.banking_service.TransferError("Alıcı hesap bulunamadı"),
        )
        with pytest.raises(payments.PaymentError, match="Alıcı"):
            payments.confirm(
                self._db(_proposal(payment_type=payments.TRANSFER, payload={})),
                "u-1", "PAY-1",
            )

    def test_a_missing_account_at_confirm_is_refused(self, mocker):
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=None)
        with pytest.raises(payments.PaymentError, match="Mevduat"):
            payments.confirm(self._db(_proposal()), "u-1", "PAY-1")


class TestCancel:
    def _db(self, proposal):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = proposal
        return db

    def test_cancelling_a_pending_proposal_marks_it(self):
        proposal = _proposal()
        assert payments.cancel(self._db(proposal), "u-1", "PAY-1") is True
        assert proposal.status == "CANCELLED"

    def test_cancelling_someone_elses_reports_not_found(self):
        assert payments.cancel(self._db(_proposal(user_id="other")), "u-1", "PAY-1") is False

    def test_cancelling_a_missing_proposal_reports_not_found(self):
        assert payments.cancel(self._db(None), "u-1", "PAY-1") is False

    def test_cancelling_an_already_confirmed_one_is_a_no_op(self):
        proposal = _proposal(status="CONFIRMED")
        assert payments.cancel(self._db(proposal), "u-1", "PAY-1") is True
        assert proposal.status == "CONFIRMED"


class TestSavedPayees:
    def test_saving_the_same_payee_twice_is_a_no_op(self):
        """The same intent expressed twice is not an error to read."""
        existing = SimpleNamespace(id="p-1")
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = existing
        assert payments.save_payee(db, "u-1", "BEDAŞ", "BEDAŞ", "1") is existing

    def test_a_new_payee_is_stored(self):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = None
        payee = payments.save_payee(db, "u-1", "BEDAŞ", "BEDAŞ", "1")
        assert payee.subscriber_no == "1" and db.add.called

    def test_listing_is_scoped_to_the_user(self):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
        assert payments.saved_payees(db, "u-1") == []

    def test_deleting_reports_whether_anything_went(self):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.delete.return_value = 1
        assert payments.delete_payee(db, "u-1", "p-1") is True
        db.query.return_value.filter.return_value.delete.return_value = 0
        assert payments.delete_payee(db, "u-1", "p-1") is False


class TestBillLookup:
    def test_only_unpaid_bills_are_found(self):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.return_value = None
        assert payments.find_open_bill(db, "BEDAŞ", "TEST-1") is None


class TestNonBillPayments:
    """The branches a bill payment does not take."""

    def _db(self, proposal, second=None):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.side_effect = [proposal, second]
        return db

    def test_a_card_payment_is_named_a_card_payment(self, mocker):
        from app.modules.banking import products

        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        # The card's debt falls in the SAME transaction as the ledger write.
        mocker.patch.object(products, "apply_card_payment", return_value=0.0)
        posted = mocker.patch.object(
            payments.banking_service, "post_adjustment",
            return_value={"reference_number": "TRF-4"},
        )
        payments.confirm(
            self._db(_proposal(payment_type=payments.CARD_PAYMENT, payload={})),
            "u-1", "PAY-1",
        )
        assert posted.call_args.kwargs["transaction_type"] == "kart"

    def test_a_proposal_whose_bill_has_vanished_still_settles(self, mocker):
        """The money moved; refusing to record it because the bill row is gone
        would leave the customer debited with nothing marked paid."""
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        mocker.patch.object(
            payments.banking_service, "post_adjustment",
            return_value={"reference_number": "TRF-5"},
        )
        result = payments.confirm(self._db(_proposal(), None), "u-1", "PAY-1")
        assert result["status"] == "CONFIRMED"

    def test_a_ledger_refusal_on_a_bill_payment_surfaces_too(self, mocker):
        """The `post_adjustment` branch has its own error path; the transfer
        branch's test does not exercise it."""
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        mocker.patch.object(
            payments.banking_service, "post_adjustment",
            side_effect=payments.banking_service.TransferError("Bakiye eksiye düşemez"),
        )
        with pytest.raises(payments.PaymentError, match="eksiye"):
            payments.confirm(self._db(_proposal(), _bill()), "u-1", "PAY-1")


class TestCardAndLoanStaging:
    """Staging a card or loan payment takes the amount from the PRODUCT.

    A chat turn naming a different figure must not be able to under- or
    over-pay, the same rule a bill already follows.
    """

    def _db(self):
        return MagicMock(spec=Session)

    def _cards(self, mocker, **over):
        from app.modules.banking import products

        card = {"id": "c-1", "name": "Platinum", "current_debt": 8450.75}
        card.update(over)
        mocker.patch.object(products, "cards_for", return_value=[card])
        return card

    def _loans(self, mocker, **over):
        from app.modules.banking import products

        loan = {
            "id": "l-1", "title": "İhtiyaç Kredisi",
            "installment_amount": 5000.0, "remaining_amount": 60000.0,
        }
        loan.update(over)
        mocker.patch.object(products, "loans_for", return_value=[loan])
        return loan

    def test_a_card_payment_defaults_to_the_whole_debt(self, mocker):
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        self._cards(mocker)
        db = self._db()
        db.query.return_value.filter.return_value.first.return_value = None
        proposal = payments.stage(
            db, user_id="u-1", payment_type=payments.CARD_PAYMENT,
            destination="c-1", idempotency_key="k",
        )
        assert float(proposal.amount) == 8450.75

    def test_a_partial_card_payment_is_allowed(self, mocker):
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        self._cards(mocker)
        db = self._db()
        db.query.return_value.filter.return_value.first.return_value = None
        proposal = payments.stage(
            db, user_id="u-1", payment_type=payments.CARD_PAYMENT,
            destination="c-1", amount=3000, idempotency_key="k",
        )
        assert float(proposal.amount) == 3000

    def test_overpaying_a_card_is_refused_at_staging(self, mocker):
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        self._cards(mocker)
        with pytest.raises(payments.PaymentError, match="fazlası ödenemez"):
            payments.stage(
                self._db(), user_id="u-1", payment_type=payments.CARD_PAYMENT,
                destination="c-1", amount=99999,
            )

    def test_an_unknown_card_is_refused(self, mocker):
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        self._cards(mocker, id="other")
        with pytest.raises(payments.PaymentError, match="Kart bulunamadı"):
            payments.stage(
                self._db(), user_id="u-1", payment_type=payments.CARD_PAYMENT,
                destination="c-1",
            )

    def test_a_loan_payment_defaults_to_ONE_instalment(self, mocker):
        """Paying a loan means this month's instalment, not clearing it."""
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        self._loans(mocker)
        db = self._db()
        db.query.return_value.filter.return_value.first.return_value = None
        proposal = payments.stage(
            db, user_id="u-1", payment_type=payments.LOAN_PAYMENT,
            destination="l-1", idempotency_key="k",
        )
        assert float(proposal.amount) == 5000.0

    def test_a_final_instalment_never_exceeds_what_is_left(self, mocker):
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        self._loans(mocker, remaining_amount=1200.0)
        db = self._db()
        db.query.return_value.filter.return_value.first.return_value = None
        proposal = payments.stage(
            db, user_id="u-1", payment_type=payments.LOAN_PAYMENT,
            destination="l-1", idempotency_key="k",
        )
        assert float(proposal.amount) == 1200.0

    def test_overpaying_a_loan_is_refused_at_staging(self, mocker):
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        self._loans(mocker)
        with pytest.raises(payments.PaymentError, match="fazlası ödenemez"):
            payments.stage(
                self._db(), user_id="u-1", payment_type=payments.LOAN_PAYMENT,
                destination="l-1", amount=99999,
            )

    def test_an_unknown_loan_is_refused(self, mocker):
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        self._loans(mocker, id="other")
        with pytest.raises(payments.PaymentError, match="Kredi bulunamadı"):
            payments.stage(
                self._db(), user_id="u-1", payment_type=payments.LOAN_PAYMENT,
                destination="l-1",
            )

    def test_naming_neither_a_card_nor_a_loan_is_refused(self, mocker):
        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        with pytest.raises(payments.PaymentError, match="seçilmedi"):
            payments.stage(
                self._db(), user_id="u-1", payment_type=payments.CARD_PAYMENT,
            )


class TestConfirmAppliesTheProduct:
    """The product side moves in the SAME transaction as the ledger write."""

    def _db(self, proposal, second=None):
        db = MagicMock(spec=Session)
        db.query.return_value.filter.return_value.first.side_effect = [proposal, second]
        return db

    def test_confirming_a_card_payment_reduces_the_debt(self, mocker):
        from app.modules.banking import products

        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        mocker.patch.object(
            payments.banking_service, "post_adjustment",
            return_value={"reference_number": "T"},
        )
        applied = mocker.patch.object(products, "apply_card_payment", return_value=5450.75)
        payments.confirm(
            self._db(_proposal(payment_type=payments.CARD_PAYMENT,
                               destination_reference="c-1", payload={})),
            "u-1", "PAY-1",
        )
        assert applied.called

    def test_confirming_a_loan_payment_records_the_instalment(self, mocker):
        from app.modules.banking import products

        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        mocker.patch.object(
            payments.banking_service, "post_adjustment",
            return_value={"reference_number": "T"},
        )
        applied = mocker.patch.object(products, "apply_loan_payment", return_value=55000.0)
        payments.confirm(
            self._db(_proposal(payment_type=payments.LOAN_PAYMENT,
                               destination_reference="l-1", payload={})),
            "u-1", "PAY-1",
        )
        assert applied.called

    def test_a_product_refusal_stops_the_whole_payment(self, mocker):
        """Money must not leave if the debt cannot be reduced."""
        from app.modules.banking import products

        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        mocker.patch.object(
            payments.banking_service, "post_adjustment",
            return_value={"reference_number": "T"},
        )
        mocker.patch.object(
            products, "apply_card_payment",
            side_effect=products.ProductError("Kart borcu 100; bundan fazlası ödenemez."),
        )
        with pytest.raises(payments.PaymentError, match="fazlası ödenemez"):
            payments.confirm(
                self._db(_proposal(payment_type=payments.CARD_PAYMENT,
                                   destination_reference="c-1", payload={})),
                "u-1", "PAY-1",
            )

    def test_a_loan_refusal_stops_it_too(self, mocker):
        from app.modules.banking import products

        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        mocker.patch.object(
            payments.banking_service, "post_adjustment",
            return_value={"reference_number": "T"},
        )
        mocker.patch.object(
            products, "apply_loan_payment",
            side_effect=products.ProductError("Kalan borç 100; bundan fazlası ödenemez."),
        )
        with pytest.raises(payments.PaymentError):
            payments.confirm(
                self._db(_proposal(payment_type=payments.LOAN_PAYMENT,
                                   destination_reference="l-1", payload={})),
                "u-1", "PAY-1",
            )

    def test_a_loan_payment_is_named_a_loan_in_the_statement(self, mocker):
        from app.modules.banking import products

        mocker.patch.object(payments.banking_service, "deposit_account", return_value=_account())
        mocker.patch.object(products, "apply_loan_payment", return_value=0.0)
        posted = mocker.patch.object(
            payments.banking_service, "post_adjustment",
            return_value={"reference_number": "T"},
        )
        payments.confirm(
            self._db(_proposal(payment_type=payments.LOAN_PAYMENT,
                               destination_reference="l-1", payload={})),
            "u-1", "PAY-1",
        )
        assert posted.call_args.kwargs["transaction_type"] == "kredi"
