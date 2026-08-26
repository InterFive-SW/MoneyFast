"""Apply the committed per-user seed files to the local database.

Runs on **every** backend start, from `docker-entrypoint.sh`, straight after
`alembic upgrade head`. That placement is not incidental: the seeds reference
`investment.investment_products`, which the migrations create, so the load has
to happen after them and inside the same container that applies them. The
previous arrangement -- a separate compose service gated on `base-db` being
healthy -- could run before any migration had touched the schema.

Two rules make running it every time safe.

**Skip a user who is already here under a different id.** Every seed file
carries a `-- moneyfast:user id=... tc=...` header. `public.users` has unique
indexes on `tc_no` and `email`, so a re-registered person would not produce a
duplicate users row -- ON CONFLICT drops it. The damage is downstream: the
file's accounts, positions and messages all carry the *seed's* user id, and
modules deliberately do not foreign-key across schemas (CLAUDE.md, "shared/
kuralı"), so nothing would reject them. They would simply attach to an id no
user has. Orphans, not duplicates, are the real failure mode, and the only
point at which they can be prevented is before the file is opened.

**One transaction per file.** A file applies whole or not at all. Half a user
-- an account with no positions, conversations with no messages -- is worse
than no user, because it looks like it worked.

An empty or missing `seeds/` is not an error. It is what a teammate has before
anyone's first export lands, and the app has to start anyway.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Iterator

from sqlalchemy import text

from app.core.database import SessionLocal

log = logging.getLogger("moneyfast.seeds")

#: Same override as the exporter: inside the image the code lives at /app, so
#: walking up from __file__ finds "/" rather than the repo root.
SEEDS = Path(os.getenv("SEEDS_DIR") or (Path(__file__).resolve().parents[2] / "seeds"))

#: The exporter's header line. Absent means a hand-written or pre-header file;
#: those are loaded without the ownership check rather than refused, since
#: ON CONFLICT still makes them idempotent.
_HEADER = re.compile(r"^--\s*moneyfast:user\s+id=(\S+)\s+tc=(\S+)\s*$", re.M)


def _statements(sql: str) -> Iterator[str]:
    """Split a seed file into statements.

    Comment lines are dropped first, then the rest is split on a
    semicolon-at-end-of-line. Both steps lean on the same property: the
    exporter puts every statement on a single line. So no line can *begin*
    with `--` except a real comment, and a `;` inside a string literal is
    never the last character of a line. A general SQL parser would be a lot
    of code defending against input this module is the sole producer of.
    """
    body = "\n".join(
        line for line in sql.splitlines() if not line.lstrip().startswith("--")
    )
    for chunk in body.split(";\n"):
        statement = chunk.strip().rstrip(";").strip()
        if statement:
            yield statement


def _owned_elsewhere(session, uid: str, tc: str) -> bool:
    """True when this TC is already someone else's row on this machine."""
    existing = session.execute(
        text("SELECT id FROM public.users WHERE tc_no = :tc"), {"tc": tc}
    ).scalar()
    return existing is not None and str(existing) != uid


def load_file(session, path: Path) -> str:
    """Apply one seed file. Returns what happened, for the log."""
    sql = path.read_text(encoding="utf-8")
    header = _HEADER.search(sql)

    if header and _owned_elsewhere(session, header.group(1), header.group(2)):
        return "skipped (TC already belongs to a different local user)"

    count = 0
    for statement in _statements(sql):
        session.execute(text(statement))
        count += 1
    session.commit()
    return f"{count} statements"


def load_all(session, seeds: Path = SEEDS) -> int:
    """Apply every user seed file. Returns the number of files applied."""
    files = sorted((seeds / "users").glob("*.sql"))
    if not files:
        log.info("no seed files under %s; nothing to load", seeds / "users")
        return 0

    applied = 0
    for path in files:
        try:
            outcome = load_file(session, path)
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop boot
            session.rollback()
            log.error("seed %s failed, skipped: %s", path.name, exc)
            continue
        applied += 1
        log.info("seed %s: %s", path.name, outcome)
    return applied


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    session = SessionLocal()
    try:
        load_all(session)
    finally:
        session.close()


if __name__ == "__main__":
    main()
