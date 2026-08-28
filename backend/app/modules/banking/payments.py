"""Staged payments: propose first, move money only on confirmation.

The investment module already holds this contract for orders. Money movement
gets the same one, for the same reason: an assistant that acts on its own
reading of "evet" is an assistant that can empty an account on a misheard
word. Staging produces a record and nothing else; only `confirm` touches a
balance, and only when the user pressed the button themselves.

One staging path covers transfers, bill payments and card payments so there is
a single place where money leaves an account, and a single thing to audit.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from . import service as banking_service
from .models import Bill, PaymentProposal, SavedPayee

log = logging.getLogger("moneyfast.banking.payments")

#: Long enough to read the confirmation, short enough that a forgotten
#: proposal cannot be confirmed against a balance that has since changed.
PROPOSAL_TTL_MINUTES = 15

TRANSFER = "TRANSFER"
BILL_PAYMENT = "BILL_PAYMENT"
CARD_PAYMENT = "CARD_PAYMENT"
LOAN_PAYMENT = "LOAN_PAYMENT"


class PaymentError(Exception):
    """Well-formed but not applicable: balance, ownership, state."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _proposal_id(idempotency_key: str) -> str:
    """Derive the id from the key, so a retried stage re-reads one proposal.

    Without this a retry mints a second proposal and the user is looking at two
    pending payments for one intent -- either of which could be confirmed.
    """
    digest = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    return f"PAY-{digest[:16].upper()}"


def find_open_bill(db: Session, institution: str, subscriber_no: str) -> Optional[Bill]:
    """The unpaid bill for a subscriber number, if there is one.

    Looked up rather than owned: the number on the paper is the key, and
    whoever holds the paper can pay it.
    """
    return (
        db.query(Bill)
        .filter(
            Bill.institution == institution,
            Bill.subscriber_no == subscriber_no,
            Bill.status == "pending",
        )
        .first()
    )


def stage(
    db: Session,
    *,
    user_id: str,
    payment_type: str,
    amount: Optional[float] = None,
    destination: Optional[str] = None,
    institution: Optional[str] = None,
    subscriber_no: Optional[str] = None,
    description: Optional[str] = None,
    idempotency_key: Optional[str] = None,
) -> PaymentProposal:
    """Prepare a payment. Nothing moves.

    The balance is checked here AND again at confirm. Twice, because two
    proposals can be staged against one balance and then both confirmed --
    checking only at staging authorises the same money twice.
    """
    # The vadesiz account explicitly. `accounts_for(...)[0]` meant this only
    # while everyone had one account; with a vadeli account it is a coincidence.
    source = banking_service.deposit_account(db, user_id)
    if source is None:
        raise PaymentError("Mevduat hesabınız bulunamadı.")

    bill: Optional[Bill] = None
    if payment_type == BILL_PAYMENT:
        if not institution or not subscriber_no:
            raise PaymentError("Kurum ve abone numarası gerekli.")
        bill = find_open_bill(db, institution, subscriber_no)
        if bill is None:
            raise PaymentError(
                f"{institution} / {subscriber_no} için ödenmemiş fatura bulunamadı."
            )
        # The amount is the bill's, never the caller's. A chat turn that named
        # a different figure must not be able to under- or over-pay.
        amount = float(bill.amount)
        destination = subscriber_no
        description = description or f"{institution} fatura ödemesi"

    if payment_type in (CARD_PAYMENT, LOAN_PAYMENT):
        if not destination:
            raise PaymentError(
                "Ödenecek kart veya kredi seçilmedi."
            )
        from . import products

        if payment_type == CARD_PAYMENT:
            card = next(
                (c for c in products.cards_for(db, user_id) if c["id"] == destination),
                None,
            )
            if card is None:
                raise PaymentError("Kart bulunamadı.")
            # Default to the whole debt; a partial payment names its amount.
            amount = amount or card["current_debt"]
            if amount > card["current_debt"]:
                raise PaymentError(
                    f"Kart borcu {card['current_debt']:,.2f}; bundan fazlası ödenemez."
                )
            description = description or f"{card['name']} kart borcu ödemesi"
        else:
            loan = next(
                (l for l in products.loans_for(db, user_id) if l["id"] == destination),
                None,
            )
            if loan is None:
                raise PaymentError("Kredi bulunamadı.")
            # One instalment unless told otherwise -- paying a loan means
            # paying this month's instalment, not clearing the balance.
            amount = amount or min(loan["installment_amount"], loan["remaining_amount"])
            if amount > loan["remaining_amount"]:
                raise PaymentError(
                    f"Kalan borç {loan['remaining_amount']:,.2f}; bundan fazlası ödenemez."
                )
            description = description or f"{loan['title']} taksit ödemesi"

    if amount is None or amount <= 0:
        raise PaymentError("Tutar sıfırdan büyük olmalı.")

    if payment_type == TRANSFER and not destination:
        raise PaymentError("Alıcı hesap gerekli.")

    if float(source.balance) < amount:
        raise PaymentError(
            f"Bakiye yetersiz: {amount:,.2f} {source.currency_code} gerekiyor, "
            f"hesabınızda {float(source.balance):,.2f} {source.currency_code} var."
        )

    key = idempotency_key or str(uuid.uuid4())
    proposal_id = _proposal_id(key)

    existing = db.query(PaymentProposal).filter(PaymentProposal.id == proposal_id).first()
    if existing is not None:
        return existing

    proposal = PaymentProposal(
        id=proposal_id,
        user_id=user_id,
        idempotency_key=key,
        status="PENDING",
        payment_type=payment_type,
        source_account_id=source.account_number,
        destination_reference=destination,
        amount=round(float(amount), 2),
        currency_code=source.currency_code,
        # What was staged, verbatim: the confirm screen shows this rather than
        # re-deriving figures that may have moved since.
        payload={
            "institution": institution,
            "subscriber_no": subscriber_no,
            "bill_id": bill.id if bill is not None else None,
            "description": description,
            "source_account": source.account_number,
            "balance_before": float(source.balance),
        },
        expires_at=_now() + timedelta(minutes=PROPOSAL_TTL_MINUTES),
        audit_id=str(uuid.uuid4()),
    )
    db.add(proposal)
    db.commit()
    log.info("staged %s %s for %s: %.2f", payment_type, proposal_id, user_id, amount)
    return proposal


def confirm(db: Session, user_id: str, proposal_id: str) -> dict[str, Any]:
    """Apply a staged payment. Ledger write and status change, one transaction.

    Committing them separately would leave a window in which money has moved
    and the proposal still reads PENDING -- confirmable a second time.
    """
    proposal = (
        db.query(PaymentProposal)
        .filter(PaymentProposal.id == proposal_id)
        .first()
    )
    if proposal is None or proposal.user_id != user_id:
        # Indistinguishable from "not found": that a proposal exists but is
        # someone else's is already more than the caller should learn.
        raise PaymentError("Öneri bulunamadı.")
    if proposal.status != "PENDING":
        raise PaymentError("Bu öneri zaten sonuçlanmış.")
    if proposal.expires_at <= _now():
        proposal.status = "EXPIRED"
        db.commit()
        raise PaymentError("Önerinin süresi doldu, lütfen yeniden hazırlayın.")

    # The vadesiz account explicitly. `accounts_for(...)[0]` meant this only
    # while everyone had one account; with a vadeli account it is a coincidence.
    source = banking_service.deposit_account(db, user_id)
    if source is None:
        raise PaymentError("Mevduat hesabınız bulunamadı.")

    amount = float(proposal.amount)
    # Checked again. The balance may have moved since staging -- another
    # proposal confirmed, a transfer sent from the panel.
    if float(source.balance) < amount:
        raise PaymentError(
            f"Bakiye yetersiz: {amount:,.2f} {source.currency_code} gerekiyor, "
            f"hesabınızda {float(source.balance):,.2f} {source.currency_code} var."
        )

    if proposal.payment_type == TRANSFER:
        try:
            result = banking_service.transfer(
                db,
                user_id=user_id,
                source_reference=source.account_number,
                destination_reference=proposal.destination_reference or "",
                amount=amount,
                description=(proposal.payload or {}).get("description"),
            )
        except banking_service.TransferError as exc:
            raise PaymentError(str(exc)) from exc
        reference = result["reference_number"]
    else:
        label = (proposal.payload or {}).get("description") or "Ödeme"
        try:
            # Named for what it is. Every non-transfer payment used to land in
            # the statement as "duzeltme", so a customer reading their own
            # history saw an admin correction where they had paid a bill.
            result = banking_service.post_adjustment(
                db, source, -amount, description=label, actor=user_id,
                transaction_type={
                    BILL_PAYMENT: "fatura",
                    CARD_PAYMENT: "kart",
                    LOAN_PAYMENT: "kredi",
                }.get(proposal.payment_type, "odeme"),
            )
        except banking_service.TransferError as exc:
            raise PaymentError(str(exc)) from exc
        reference = result["reference_number"]

        # The product side moves in the SAME transaction as the ledger write.
        # A card whose debt fell without the money leaving, or money that left
        # without the debt falling, are both worse than a refused payment.
        from . import products

        if proposal.payment_type == CARD_PAYMENT and proposal.destination_reference:
            try:
                products.apply_card_payment(
                    db, user_id, proposal.destination_reference, amount,
                )
            except products.ProductError as exc:
                raise PaymentError(str(exc)) from exc
        elif proposal.payment_type == LOAN_PAYMENT and proposal.destination_reference:
            try:
                products.apply_loan_payment(
                    db, user_id, proposal.destination_reference, amount,
                )
            except products.ProductError as exc:
                raise PaymentError(str(exc)) from exc

        bill_id = (proposal.payload or {}).get("bill_id")
        if bill_id:
            bill = db.query(Bill).filter(Bill.id == bill_id).first()
            if bill is not None:
                bill.status = "paid"
                bill.paid_by = user_id
                bill.paid_at = _now()

    proposal.status = "CONFIRMED"
    proposal.confirmed_at = _now()
    db.commit()

    refreshed = banking_service.deposit_account(db, user_id)
    log.info("confirmed %s for %s: %.2f", proposal_id, user_id, amount)
    return {
        "proposal_id": proposal.id,
        "status": "CONFIRMED",
        "reference_number": reference,
        "amount": amount,
        "currency": proposal.currency_code,
        "balance_after": float(refreshed.balance) if refreshed else None,
    }


def cancel(db: Session, user_id: str, proposal_id: str) -> bool:
    """Withdraw a staged payment. Idempotent for an already-cancelled one."""
    proposal = (
        db.query(PaymentProposal)
        .filter(PaymentProposal.id == proposal_id)
        .first()
    )
    if proposal is None or proposal.user_id != user_id:
        return False
    if proposal.status == "PENDING":
        proposal.status = "CANCELLED"
        proposal.cancelled_at = _now()
        db.commit()
    return True


def save_payee(
    db: Session, user_id: str, label: str, institution: str, subscriber_no: str,
) -> SavedPayee:
    """Keep a subscriber number. Saving the same one twice is a no-op.

    The same intent expressed twice is not an error the user should have to
    read, so an existing row is returned rather than a 409.
    """
    existing = (
        db.query(SavedPayee)
        .filter(
            SavedPayee.user_id == user_id,
            SavedPayee.institution == institution,
            SavedPayee.subscriber_no == subscriber_no,
        )
        .first()
    )
    if existing is not None:
        return existing

    payee = SavedPayee(
        user_id=user_id, label=label, institution=institution,
        subscriber_no=subscriber_no,
    )
    db.add(payee)
    db.commit()
    return payee


def saved_payees(db: Session, user_id: str) -> list[SavedPayee]:
    return (
        db.query(SavedPayee)
        .filter(SavedPayee.user_id == user_id)
        .order_by(SavedPayee.created_at)
        .all()
    )


def delete_payee(db: Session, user_id: str, payee_id: str) -> bool:
    deleted = (
        db.query(SavedPayee)
        .filter(SavedPayee.id == payee_id, SavedPayee.user_id == user_id)
        .delete()
    )
    db.commit()
    return bool(deleted)
