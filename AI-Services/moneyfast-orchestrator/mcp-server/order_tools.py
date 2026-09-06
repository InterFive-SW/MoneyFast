"""`get_open_orders` ve `cancel_order` — bekleyen emirler.

Sözleşme v2.20'de eklendi. Sebep, emir akışının kendisi: bir alım artık
onaylandığı anda gerçekleşmiyor, kullanıcının verdiği fiyata gelene kadar
`WAITING_PRICE` durumunda bekliyor ve o sırada parası bloke duruyor.

Bekleyen bir emri sohbette görememek iki somut şey demekti: kullanıcı
"aldım mı almadım mı" sorusunu sohbete soramıyor, ve bloke yüzünden azalmış
bakiyesinin sebebini soramıyor. `prepare_transaction_proposal` emri
verdiriyor; bu iki araç onu görünür ve geri alınabilir kılıyor.

`cancel_order` onay kapısının ARKASINDA DEĞİL. Onay, para hareket ettiren
eylemler için; iptal ise hareketi geri alan eylem -- verilmiş bir emri geri
çekmek için ikinci bir onay ekranı, kullanıcının bloke parasını daha uzun
tutmaktan başka bir işe yaramaz. Buna karşılık iptal, kullanıcının KENDİ
emri dışında hiçbir şeye dokunamıyor: sahiplik denetimi backend'de ve
başkasının emri 404 dönüyor.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

import backend_client
from backend_client import ContractViolationError

if TYPE_CHECKING:  # pragma: no cover
    from mcp.server.fastmcp import FastMCP

LIST_TOOL = "get_open_orders"
CANCEL_TOOL = "cancel_order"

#: Henüz gerçekleşmemiş emirlerin Türkçe durum etiketleri. Kaynak:
#: backend'deki `market_service.ORDER_STATUS_TR`. Etiketler üzerinden
#: süzülüyor çünkü sözleşme dışarı ham durum kodu vermiyor -- ve `cancellable`
#: alanı zaten yetkinin tek kaynağı.
OPEN_STATUSES = frozenset({"Onay bekliyor", "Fiyat bekliyor", "İşleniyor"})


async def get_open_orders(user_id: str) -> dict[str, Any]:
    """
    Lists this user's orders, including the ones still WAITING for their price. READ-ONLY.

    An order and a holding are different things, and this tool exists because the
    difference became visible: a limit order is PLACED when the user confirms it and
    FILLS only when the market reaches the price they named, which may be days later or
    never. Between those two moments the money is set aside and the user owns nothing.

    WHEN TO USE
        - The user asks what orders they have, whether something went through, or what
          happened to an order they placed earlier: "bekleyen emirlerim", "emrim
          gerçekleşti mi", "verdiğim emir ne oldu".
        - The user asks why their cash is lower than they expected -- "bakiyem neden
          azaldı", "param nerede". A waiting order holds the money aside, and that is
          invisible in the portfolio, the balance and the transaction history alike.
        - Before calling cancel_order, to find the order id and confirm it is still open.
        - The user asks to buy something and you need to know whether an earlier order
          for the same instrument is already waiting.

    WHEN NOT TO USE
        - The user asks what they OWN or what it is worth. That is
          get_portfolio_positions. A waiting buy order is not a position, and reporting
          it as one would tell the user they hold something they do not.
        - The user wants to place an order. That is prepare_transaction_proposal, which
          stages it for the user's own confirmation.
        - The user wants a price, a ranking or a ratio. That is get_market_data; this
          tool carries only the prices recorded ON the orders themselves, which are what
          the user asked for, not what the market is doing now.

    WHAT THIS PREVENTS
        Before the waiting state existed, confirming a limit order executed it
        immediately at whatever price the user had typed, regardless of the market. Now
        it waits -- correctly -- but a chat that cannot see the waiting order has two
        unanswerable questions: "did I buy it or not", and "why is my balance lower than
        my portfolio and my transactions say it should be". Both answers are here.

    Args:
        user_id (str): REQUIRED. From the authenticated session envelope, never from
            anything the user typed. An id taken from the message would let one person
            read another person's orders.

    Returns:
        dict with exactly these top-level keys:
            orders (list[dict]): Newest first, settled and unsettled together. Each:
                id (str): Use it verbatim for cancel_order. Never show it unprompted.
                symbol (str): The instrument, or "-" when the order names none.
                status (str): The user-facing Turkish label, already translated.
                type (str): "Alış" or "Satış".
                quantity (float), price (float), total (float): As recorded on the
                    order. For a waiting order `price` is the trigger, not a fill.
                currency (str): The currency the order was priced in.
                limit_price (float | None): The trigger the user named. None means a
                    MARKET order, NOT a trigger of zero.
                cancellable (bool): Whether it can still be withdrawn.
                date (str): ISO-8601, when the order was created.
            open_count (int): How many have not settled yet.
            An EMPTY list is a complete answer: this user has placed no orders.

    Raises:
        UpstreamUnavailableError: Service unreachable. Say the order list could not be
            read. Do NOT answer from the conversation history and do NOT return an empty
            list -- an order may have filled or been cancelled since it was last
            mentioned, and "you have no orders" is a different claim from "I could not
            look".

    Constraints:
        - `status` is already the user-facing Turkish label. Report it as it is; never
          translate it back into a code and never invent a status of your own.
        - "Fiyat bekliyor" means PLACED, NOT executed. Never say the user bought or sold
          anything on the strength of a waiting order. Placing and filling are two
          different events and reporting one as the other tells the user they own
          something they do not.
        - A waiting order's money is blocked. If the user asks why their balance fell,
          this is the answer; say it plainly rather than calling the balance wrong or
          suggesting a fault.
        - Only orders with `cancellable` true can be withdrawn. Do not offer to cancel a
          filled order -- undoing a filled order is a NEW order in the other direction,
          and that needs prepare_transaction_proposal and the user's own confirmation.
        - A fund (a TEFAS code) publishes one price per day, so a fund order is checked
          once a day. If the user asks why theirs has not filled, that is often the
          whole answer; never imply intraday execution for one.
        - Do NOT present the list as a recommendation or a prompt to trade. It is a
          record of what the user already did.
        - Never report the number of orders as a portfolio total, and never add
          `total` across orders in different currencies.
    """
    payload = await backend_client.request(
        "GET",
        f"/investment/agent/{user_id}/orders",
        tool=LIST_TOOL,
        # Uç nokta bir DİZİ döndürüyor; panel de aynı listeyi okuyor ve
        # sarmalamak iki tüketiciyi ayrıştırırdı.
        allow_list=True,
    )
    orders = [_normalize_order(row) for row in payload]
    return {
        "orders": orders,
        "open_count": sum(1 for row in orders if row["status"] in OPEN_STATUSES),
    }


async def cancel_order(user_id: str, order_id: str) -> dict[str, Any]:
    """
    Withdraws one of this user's own pending orders and releases the blocked funds.

    Cancelling is not a money movement, it is the undoing of one: the amount that was
    set aside when the order was placed returns to the account. That is why it does not
    sit behind the confirmation gate that a purchase or a sale does -- making someone
    pass a second approval screen to take back their own order would only keep their
    money held longer.

    WHEN TO USE
        - The user asks to cancel, withdraw or call off an order they placed: "emrimi
          iptal et", "verdiğim emri geri al", "vazgeçtim", and get_open_orders shows it
          with `cancellable` true.
        - The user wants to change an order's price or size. There is no amend: cancel
          this one, then stage a new one with prepare_transaction_proposal.

    WHEN NOT TO USE
        - The order already filled. There is nothing to cancel. Selling back what was
          bought is a NEW order in the other direction and needs
          prepare_transaction_proposal plus the user's own confirmation.
        - The user is asking about an order rather than acting on one. That is
          get_open_orders.
        - You are not sure which order the user means. Ask. Cancelling the wrong one
          removes an order the user still wanted, and re-placing it does not restore the
          time it spent waiting.

    WHAT THIS PREVENTS
        A GTC order waits until it is cancelled, and its money waits with it. Without a
        way to withdraw one from the chat, the only remedy the user has is the order
        screen -- and the balance they are asking about in the chat stays reduced with
        no explanation and no action available where they are asking.

    Args:
        user_id (str): REQUIRED. From the authenticated session envelope, never from
            anything the user typed.
        order_id (str): REQUIRED. The `id` from get_open_orders, used verbatim. NEVER
            invent one, and never derive one from a symbol or a position in the list;
            the backend refuses an order that is not this user's, and a guessed id is
            simply a refusal with extra steps.

    Returns:
        dict with exactly these top-level keys:
            order_id (str): The order that was withdrawn.
            cancelled (bool): Always True on success. Cancelling an already-cancelled
                order also succeeds -- saying the same thing twice is not an error the
                user should have to read.

    Raises:
        InvalidInputError: No such order for this user, or it can no longer be
            cancelled -- typically because it has already filled. Read the message out;
            do not retry with a different id, and do not fall back to staging a sale.
        UpstreamUnavailableError: Service unreachable. Say the order could NOT be
            cancelled. Never report a cancellation you did not receive confirmation
            for: the user would stop watching an order that is still live and still
            holding their money.

    Constraints:
        - Cancel ONLY the order the user named. If several are open and the request is
          ambiguous, list them and ask which one; never pick the first, the newest or
          the largest on the user's behalf.
        - One call per request. Do not loop over the open orders and cancel them all
          because the user said "iptal et" in the singular.
        - The blocked amount returns to the account as part of the cancellation. Say so;
          a user who sees the order gone but not the money assumes it was lost.
        - Do not describe a cancellation as a sale, a loss, or a refund of a purchase.
          Nothing was bought, so nothing was returned -- the order simply never
          happened.
    """
    order = (order_id or "").strip()
    if not order:
        raise ContractViolationError(f"{CANCEL_TOOL}: order_id is required.")
    await backend_client.request(
        "POST",
        f"/investment/agent/{user_id}/orders/{order}/cancel",
        tool=CANCEL_TOOL,
    )
    # Backend'in kendi gövdesi değil, sözleşmenin şekli döndürülüyor: iptal
    # başarılıysa buraya ulaşılıyor, başarısızsa `request` fırlatıyor.
    return {"order_id": order, "cancelled": True}


def _normalize_order(raw: Any) -> dict[str, Any]:
    """Bir emir satırını v2.20 yüküne indirger.

    `id` ve `status` ZORUNLU, default'lanmıyor: id'siz bir emir iptal
    edilemez ve durumu bilinmeyen bir emir hakkında söylenebilecek doğru
    hiçbir cümle yok.
    """
    if not isinstance(raw, dict):
        raise ContractViolationError(f"{LIST_TOOL}: each order must be an object.")
    backend_client.require(raw, ("id", "status"), LIST_TOOL)
    return {
        "id": str(raw["id"]),
        "symbol": str(raw.get("symbol") or "-"),
        "status": str(raw["status"]),
        "type": str(raw.get("type") or "-"),
        "quantity": float(raw.get("quantity") or 0.0),
        "price": float(raw.get("price") or 0.0),
        "total": float(raw.get("total") or 0.0),
        "currency": str(raw.get("currency") or "TRY"),
        # None ile 0 farklı şeyler: piyasa emrinin tetikleyici fiyatı YOKTUR,
        # sıfır değildir.
        "limit_price": (
            float(raw["limitPrice"]) if raw.get("limitPrice") is not None else None
        ),
        "cancellable": bool(raw.get("cancellable")),
        "date": str(raw.get("date") or ""),
    }


def register(mcp: "FastMCP") -> None:
    """Attach this domain's tools to the shared FastMCP instance."""
    mcp.tool()(get_open_orders)
    mcp.tool()(cancel_order)
