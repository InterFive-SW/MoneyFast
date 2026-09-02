"""Risk profile persistence.

`infra/intertech.sql` sketches `auth.risk_profiles` and `auth.risk_assessments`
under the auth schema. They live here instead, under `risk`, because CLAUDE.md
puts a model in the module that OWNS it and `auth` owns identity, not risk
tolerance. `user_id` is a bare column with no foreign key, the same way
`ai.conversations` references a user: the modules share a database but not an
import graph.

Two tables rather than one, on purpose:

* `risk_assessments` is append-only. Every submission is kept, so "what did I
  say last month" has an answer and a changed tolerance is visible as a change
  rather than as a silent overwrite.
* `risk_profiles` is the one row that counts right now, so every read does not
  have to sort the history.
"""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

SCHEMA = "risk"


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class RiskAssessment(Base):
    """One completed questionnaire. Never updated, never deleted."""

    __tablename__ = "risk_assessments"
    __table_args__ = (
        Index("idx_risk_assessments_user_created", "user_id", "created_at"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    #: The questionnaire this was scored against. An old row is never
    #: re-scored under new weights; the score someone saw is the score that
    #: stays on their record.
    questionnaire_version: Mapped[str] = mapped_column(String(16), nullable=False)
    #: The raw answers, so a scoring change can be audited against what was
    #: actually said rather than against its result.
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    raw_score: Mapped[float] = mapped_column(Float, nullable=False)
    tolerance_level: Mapped[str] = mapped_column(String(16), nullable=False)
    investment_horizon: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class RiskProfile(Base):
    """The tolerance currently in effect. One row per user."""

    __tablename__ = "risk_profiles"
    __table_args__ = ({"schema": SCHEMA},)

    #: The user is the key. A second profile for the same person would mean
    #: two answers to "what do you tolerate", and nothing could say which one
    #: the comparison used.
    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    tolerance_level: Mapped[str] = mapped_column(String(16), nullable=False)
    investment_horizon: Mapped[str] = mapped_column(String(32), nullable=False)
    #: Points at the assessment this was derived from, so the profile is
    #: always traceable to the answers behind it.
    latest_assessment_id: Mapped[str] = mapped_column(String, nullable=False)
    questionnaire_version: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Ürün grubu başına yeterlilik, uygunluk testinin ürettiği hâliyle.
    #:
    #: Profilde denormalize duruyor, değerlendirme satırından okunmuyor:
    #: `tolerance_level` da öyle ve aynı sebeple -- yürürlükteki profili
    #: okumak her seferinde bir birleştirme gerektirmemeli.
    #:
    #: v1 ile doldurulmuş bir profilde NULL. Boş liste ile null aynı şey
    #: değil: null "sorulmadı", boş liste "soruldu, hiçbiri uygun çıkmadı"
    #: demek olurdu ve ikincisi o kullanıcı için doğru değil.
    product_groups: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )


class RiskSnapshot(Base):
    """One day's measured risk, kept so the score has a history.

    Written by `GET /profile` rather than by a scheduled job: the endpoint
    already does the whole computation, so a separate worker would recompute
    the same numbers on a different clock and the two would drift.

    `captured_on` is a DATE and unique per user, which does the throttling in
    the schema rather than in a code path someone can forget: the second read
    on the same day cannot insert a second row, so the table stays bounded at
    roughly 365 rows per user per year.

    Only the DEFAULT window is recorded. A series that mixed a 3-month score
    with a 1-year one would show a jump the portfolio never made -- the change
    would be in the question, not in the answer.
    """

    __tablename__ = "risk_snapshots"
    __table_args__ = (
        UniqueConstraint("user_id", "captured_on", name="uq_risk_snapshots_user_day"),
        Index("idx_risk_snapshots_user_day", "user_id", "captured_on"),
        {"schema": SCHEMA},
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    captured_on: Mapped[date] = mapped_column(Date, nullable=False)
    #: Nullable throughout: a day on which nothing could be measured is worth
    #: recording as unmeasured, and zeroes would draw a crash on the chart.
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    level: Mapped[str | None] = mapped_column(String(16), nullable=True)
    volatility: Mapped[float | None] = mapped_column(Float, nullable=True)
    hhi: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_drawdown: Mapped[float | None] = mapped_column(Float, nullable=True)
    position_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False
    )
