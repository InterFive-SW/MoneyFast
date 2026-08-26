"""Export the hand-made database state to reviewable, per-user SQL files.

The problem this solves: a teammate who clones the repo and runs
`docker compose up` gets instruments from the migrations and **no login**, so
they cannot use the app at all. Everything a person builds by using the
product — their account, portfolio, watchlist, chat history — lives only in
their own Docker volume.

One file per user, named by TC number, is what keeps this out of merge hell.
Two people adding their own test user touch two different files, so git never
has to compare their contents. Whoever owns a user owns that file.

Two properties matter more than they look:

* **Deterministic.** Every table is read with an explicit ORDER BY and written
  in that order. Without it the same data re-exports in a different row order
  and every export looks like a full rewrite — which is exactly the conflict
  storm the per-user split exists to prevent.
* **Idempotent on load.** Every statement carries ON CONFLICT DO NOTHING, so
  running the loader twice changes nothing and loading a teammate's user never
  disturbs yours.

Products, quotes, candles and news are NOT exported. Migrations seed the
instrument universe, and the ingestor produces everything else: prices and
news each cycle, and daily bars via its start-up backfill. Committing data a
service regenerates on its own means a file that churns on every pull and
that nobody needs -- candles alone were 7.5 MB of it.

    python -m scripts.export_seeds                    # every user
    python -m scripts.export_seeds --user 11111111112 # one user
    python -m scripts.export_seeds --no-chat          # skip conversations
"""

from __future__ import annotations

import argparse
import os
import re
from decimal import Decimal
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from sqlalchemy import text

from app.core.database import SessionLocal

#: Where the files land. Overridable because the path differs on the two sides
#: of the container boundary: in the image the code lives at /app, so walking
#: up from __file__ finds "/" rather than the repo root. Compose bind-mounts
#: ./seeds to /app/seeds and sets this.
SEEDS = Path(os.getenv("SEEDS_DIR") or (Path(__file__).resolve().parents[2] / "seeds"))

#: Per-user tables in FOREIGN KEY order: a row is never written before the row
#: it points at. `banking.account_transactions` needs both its transaction and
#: its account, so it comes last.
#:
#: Each entry is (table, WHERE, ORDER BY, resolve).
#:
#: `resolve` names columns whose stored value is NOT portable between machines.
#: `investment_products.id` is generated with gen_random_uuid() inside the
#: migration, so every clone has different ids -- a seed row carrying a literal
#: product_id fails the foreign key on anyone else's database. Those columns
#: are emitted as a lookup by symbol instead, which IS stable.
USER_TABLES: Sequence[tuple[str, str, str]] = (
    ("public.users", "id = :uid", "id", ()),
    ("investment.investment_accounts", "user_id = :uid", "account_number", ()),
    (
        "investment.portfolio_positions",
        "investment_account_id IN (SELECT id FROM investment.investment_accounts"
        " WHERE user_id = :uid)",
        "product_id",
        ("product_id",),
    ),
    ("investment.watchlist_items", "user_id = :uid", "created_at, id", ("product_id",)),
    ("banking.accounts", "user_id = :uid", "account_number", ()),
    (
        # No user_id of its own: a transaction belongs to whoever owns a leg.
        "banking.transactions",
        "id IN (SELECT transaction_id FROM banking.account_transactions"
        " WHERE account_id IN (SELECT id FROM banking.accounts WHERE user_id = :uid))",
        "created_at, id",
        (),
    ),
    (
        "banking.account_transactions",
        "account_id IN (SELECT id FROM banking.accounts WHERE user_id = :uid)",
        "created_at, id",
        (),
    ),
    ("banking.savings_goals", "user_id = :uid", "created_at, id", ()),
    ("investment.transaction_proposals", "user_id = :uid", "created_at, id", ()),
)

CHAT_TABLES: Sequence[tuple[str, str, str]] = (
    ("ai.conversations", "user_id = :uid", "created_at, id", ()),
    (
        "ai.messages",
        "conversation_id IN (SELECT id FROM ai.conversations WHERE user_id = :uid)",
        "created_at, id",
        (),
    ),
)


def _literal(value: Any) -> str:
    """One value as a SQL literal.

    Hand-rolled rather than delegated to the driver because the output is a
    file a human reads and reviews in a diff, not a parameterised statement.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    if isinstance(value, (datetime, date)):
        return "'" + value.isoformat() + "'"
    if isinstance(value, (dict, list)):
        import json

        return "'" + json.dumps(value, ensure_ascii=False).replace("'", "''") + "'"
    return "'" + str(value).replace("'", "''") + "'"


def _slug(text_value: str) -> str:
    """A filename-safe label. Only ever used after the TC number."""
    return re.sub(r"[^a-z0-9]+", "-", (text_value or "").lower()).strip("-") or "user"


#: How to express a non-portable id as something stable. Only product_id so
#: far; the pattern generalises if another generated key ever gets seeded.
PRODUCT_LOOKUP = "(SELECT id FROM investment.investment_products WHERE symbol = {sym})"


def _dump_table(
    session, table: str, where: str, order: str, uid: str,
    resolve: Sequence[str] = (),
) -> list[str]:
    select = "*"
    if "product_id" in resolve:
        # Carry the symbol alongside so the emitted SQL can look the id up on
        # whatever machine loads it.
        select = "t.*, (SELECT symbol FROM investment.investment_products p" \
                 " WHERE p.id = t.product_id) AS _symbol"
    rows = session.execute(
        text(f"SELECT {select} FROM {table} t WHERE {where} ORDER BY {order}"),
        {"uid": uid},
    ).mappings().all()
    if not rows:
        return []

    columns = [c for c in rows[0].keys() if c != "_symbol"]
    collist = ", ".join(f'"{c}"' for c in columns)
    out = [f"-- {table} ({len(rows)})"]
    for row in rows:
        if "product_id" in resolve:
            values = ", ".join(
                PRODUCT_LOOKUP.format(sym=_literal(row["_symbol"]))
                if c == "product_id" else _literal(row[c])
                for c in columns
            )
        else:
            values = ", ".join(_literal(row[c]) for c in columns)
        out.append(
            f"INSERT INTO {table} ({collist}) VALUES ({values})"
            f" ON CONFLICT DO NOTHING;"
        )
    out.append("")
    return out


def export_user(session, user: Any, include_chat: bool) -> Path:
    uid = str(user["id"])
    tables: Iterable[tuple[str, str, str]] = USER_TABLES
    if include_chat:
        tables = tuple(USER_TABLES) + tuple(CHAT_TABLES)

    body: list[str] = []
    for table, where, order, resolve in tables:
        body.extend(_dump_table(session, table, where, order, uid, resolve))

    header = [
        f"-- MoneyFast seed: {user['email']} ({user['tc_no']})",
        # Machine-readable, and the reason the loader can be safe rather than
        # merely idempotent. Loading is skipped outright when this TC already
        # belongs to a DIFFERENT id: ON CONFLICT would drop the users row and
        # then happily insert accounts pointing at an id nobody has, because
        # modules do not foreign-key across schemas (CLAUDE.md). Orphans, not
        # duplicates, are the failure mode this prevents.
        f"-- moneyfast:user id={uid} tc={user['tc_no']}",
        "--",
        "-- Generated by `python -m scripts.export_seeds`. One file per user so",
        "-- two people adding their own test user never touch the same file.",
        "-- Every statement is ON CONFLICT DO NOTHING: loading twice is a no-op,",
        "-- and loading someone else's user does not disturb yours.",
        "--",
        "-- Synthetic data only (see CLAUDE.md). Do not hand-edit; re-export.",
        "",
    ]
    target = SEEDS / "users" / f"{user['tc_no']}-{_slug(user['email'].split('@')[0])}.sql"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(header + body), encoding="utf-8")
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", help="TC number; default is every user")
    parser.add_argument("--no-chat", action="store_true",
                        help="skip conversations and messages")
    args = parser.parse_args()

    session = SessionLocal()
    try:
        where = "tc_no = :tc" if args.user else "TRUE"
        users = session.execute(
            text(f"SELECT * FROM public.users WHERE {where} ORDER BY created_at"),
            {"tc": args.user} if args.user else {},
        ).mappings().all()

        if not users:
            print("no users matched; nothing written")
            return

        for user in users:
            path = export_user(session, user, include_chat=not args.no_chat)
            print(f"wrote {path.relative_to(SEEDS.parent)}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
