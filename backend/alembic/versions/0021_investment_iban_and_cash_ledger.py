"""Yatırım hesabına IBAN ve nakit hareket defteri.

İki eksik birlikte kapanıyor, çünkü aynı sorunun iki yüzü:

1. `investment.investment_accounts` satırının IBAN'ı yoktu. Hesap "para
   gönder" ekranında adreslenemiyor, bankacılık arayüzünde de kimliksiz
   görünüyordu.

2. Hesabın nakit bakiyesini üç ayrı yer yazıyor -- alım/satım takası
   (`investment/service.settle`), bankacılık köprüsü
   (`banking/service.transfer_with_investment`) ve yöneticinin para ekleme
   işlemi (`admin/service.adjust_cash`) -- ve hiçbiri hareket kaydı
   bırakmıyordu. Bu yüzden hesabın "hesap hareketi" diye gösterebileceği hiçbir
   şey yoktu.

Bakiyeden geriye doğru hesaplamak çözüm değildi: yöneticinin eklediği para
hiçbir kayıtta görünmediği için yeniden oynatma sessizce kayardı. Defter bu
yüzden bankacılıktaki `account_transactions` ile aynı biçimde, satır başına
`balance_before`/`balance_after` ile tutuluyor.

Geçmiş, elde olan iki kaynaktan geri dolduruluyor: yatırım hesabını karşı
taraf gösteren virman bacakları ve onaylanmış işlem önerileri. Yürüyen bakiye
mevcut `cash_balance`'tan geriye doğru yürünerek yazılıyor. Kayıt bırakmamış
eski bir yönetici düzeltmesi varsa fark en eski satırlarda kalır; bundan
sonrası birebir doğrudur.
"""

import hashlib
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _iban_for(account_number: str) -> str:
    """`investment/service.iban_for` ile aynı hesap -- ikisi ayrışamaz.

    Kasıtlı olarak TR00: gerçek bir kontrol hanesi bu hesapları yönlendirilebilir
    gibi gösterirdi ve buradaki hiçbir şey bir ödeme ağına çıkmıyor.

    Hesap numarasının kendisi değil, özeti kullanılıyor: `TR-0003-28BFBC42`
    gibi bir numarada yalnızca birkaç rakam var ve rakamları alıp doldurmak
    iki farklı hesabı aynı IBAN'a düşürebilirdi.
    """
    digest = hashlib.sha256(str(account_number).encode("utf-8")).hexdigest()
    body = str(int(digest[:20], 16)).zfill(16)[:16]
    return f"TR00{body}00000{body[:2]}"


def upgrade() -> None:
    op.add_column(
        "investment_accounts",
        sa.Column("iban", sa.String(length=34), nullable=True),
        schema="investment",
    )

    op.create_table(
        "cash_movements",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("account_id", sa.String(), nullable=False, index=True),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.Column("amount", sa.Numeric(19, 4), nullable=False),
        sa.Column("balance_before", sa.Numeric(19, 4), nullable=False),
        sa.Column("balance_after", sa.Numeric(19, 4), nullable=False),
        sa.Column("reference", sa.String(length=64), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        schema="investment",
    )
    op.create_index(
        "idx_cash_movements_account",
        "cash_movements",
        ["account_id", "created_at"],
        schema="investment",
    )

    conn = op.get_bind()

    accounts = conn.execute(
        sa.text(
            "SELECT id, user_id, account_number, cash_balance "
            "FROM investment.investment_accounts ORDER BY account_number"
        )
    ).fetchall()

    for account in accounts:
        conn.execute(
            sa.text(
                "UPDATE investment.investment_accounts SET iban = :iban WHERE id = :id"
            ),
            {"iban": _iban_for(account.account_number), "id": account.id},
        )
        _backfill(conn, account)

    op.create_unique_constraint(
        "uq_investment_accounts_iban", "investment_accounts", ["iban"],
        schema="investment",
    )


def _backfill(conn, account) -> None:
    """Bilinen iki kaynaktan geçmiş hareketleri yazar."""
    movements = []

    # 1) Virmanlar. Bacak bankacılık hesabında duruyor ve yatırım hesabını
    #    karşı taraf gösteriyor, dolayısıyla yön TERS çevrilir: bankadan çıkan
    #    para yatırım hesabına girmiştir.
    legs = conn.execute(
        sa.text(
            "SELECT l.direction, l.amount, l.description, l.created_at, t.reference_number "
            "  FROM banking.account_transactions l "
            "  JOIN banking.transactions t ON t.id = l.transaction_id "
            " WHERE l.counterparty_iban = :account_number "
            " ORDER BY l.created_at"
        ),
        {"account_number": account.account_number},
    ).fetchall()
    for leg in legs:
        movements.append(
            {
                "direction": "CREDIT" if leg.direction == "DEBIT" else "DEBIT",
                "amount": float(leg.amount),
                "reference": leg.reference_number,
                "description": leg.description or "Virman",
                "created_at": leg.created_at,
            }
        )

    # 2) Onaylanmış alım/satımlar. Alım nakdi düşürür, satış yükseltir.
    trades = conn.execute(
        sa.text(
            "SELECT id, symbol, transaction_type, payload, confirmed_at, created_at "
            "  FROM investment.transaction_proposals "
            " WHERE status = 'CONFIRMED' AND user_id = :user_id "
            "   AND transaction_type IN ('BUY', 'SELL') "
            " ORDER BY COALESCE(confirmed_at, created_at)"
        ),
        {"user_id": account.user_id},
    ).fetchall()
    for trade in trades:
        net = _net_amount(trade.payload)
        if net is None:
            continue
        side = (trade.transaction_type or "").upper()
        movements.append(
            {
                "direction": "DEBIT" if side == "BUY" else "CREDIT",
                "amount": abs(net),
                "reference": trade.id,
                "description": f"{'Alım' if side == 'BUY' else 'Satım'} — {trade.symbol}",
                "created_at": trade.confirmed_at or trade.created_at,
            }
        )

    if not movements:
        return

    movements.sort(key=lambda m: m["created_at"])

    # Yürüyen bakiye bugünkü değerden geriye doğru: ileriye doğru yürümek için
    # açılış bakiyesini bilmek gerekir ve o kayıt hiç tutulmadı.
    balance_after = []
    running = float(account.cash_balance)
    for movement in reversed(movements):
        balance_after.append(running)
        delta = movement["amount"] if movement["direction"] == "CREDIT" else -movement["amount"]
        running = round(running - delta, 2)
    balance_after.reverse()

    for index, movement in enumerate(movements):
        after = round(balance_after[index], 2)
        delta = movement["amount"] if movement["direction"] == "CREDIT" else -movement["amount"]
        conn.execute(
            sa.text(
                "INSERT INTO investment.cash_movements "
                "(id, account_id, direction, amount, balance_before, balance_after, "
                " reference, description, created_at) "
                "VALUES (gen_random_uuid()::text, :account_id, :direction, :amount, "
                "        :balance_before, :balance_after, :reference, :description, :created_at)"
            ),
            {
                "account_id": account.id,
                "direction": movement["direction"],
                "amount": movement["amount"],
                "balance_before": round(after - delta, 2),
                "balance_after": after,
                "reference": movement["reference"],
                "description": movement["description"][:255],
                "created_at": movement["created_at"],
            },
        )


def _net_amount(payload) -> float | None:
    """Önerinin hesabın para birimindeki net tutarı.

    `estimate.net_amount` enstrümanın para biriminde; hesaba işlenen tutar
    `settle()` ile aynı şekilde kurdan geçmiş olanıdır. Kur yoksa satır
    atlanır -- 1.0 varsaymak bu projenin daha önce bedelini ödediği hata.
    """
    if not isinstance(payload, dict):
        return None
    estimate = payload.get("estimate") or {}
    net = estimate.get("net_amount")
    if net is None:
        return None
    rate = (estimate.get("fx") or {}).get("rate")
    try:
        value = float(net)
    except (TypeError, ValueError):
        return None
    if rate is not None:
        try:
            value *= float(rate)
        except (TypeError, ValueError):
            return None
    return round(value, 2)


def downgrade() -> None:
    op.drop_constraint(
        "uq_investment_accounts_iban", "investment_accounts",
        schema="investment", type_="unique",
    )
    op.drop_index("idx_cash_movements_account", table_name="cash_movements", schema="investment")
    op.drop_table("cash_movements", schema="investment")
    op.drop_column("investment_accounts", "iban", schema="investment")
