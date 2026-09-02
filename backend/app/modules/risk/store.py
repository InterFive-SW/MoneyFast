"""Database access for the risk profile.

Separate from `service.py` on purpose: that module is the calculation engine
and takes its price history through an injected callable specifically so it
never touches a session. Mixing persistence into it would undo that.

Unlike `ai_orchestrator.service.record_turn`, these do NOT swallow errors. A
chat turn is best-effort because the answer already happened and losing the log
row is the smaller harm. Here the write IS the user's action -- silently
dropping a submitted questionnaire would leave someone believing they had
declared a tolerance they had not.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from .models import RiskAssessment, RiskProfile, RiskSnapshot

log = logging.getLogger("moneyfast.risk")


def latest_profile(db: Session, user_id: str) -> Optional[RiskProfile]:
    return db.query(RiskProfile).filter(RiskProfile.user_id == user_id).first()


def record_assessment(
    db: Session, user_id: str, answers: Dict[str, str], scored: Dict[str, Any]
) -> RiskProfile:
    """Store one submission and make it the profile in effect.

    Both rows commit together. Writing the assessment without updating the
    profile would leave the comparison reading a stale tolerance while the
    history says otherwise, and the user has no way to see which one won.
    """
    # The id is generated here rather than left to the column default, which
    # SQLAlchemy only applies at flush time -- the profile row needs it before
    # then. Same reason `ai_orchestrator` does it.
    assessment = RiskAssessment(
        id=str(uuid.uuid4()),
        user_id=user_id,
        questionnaire_version=scored["version"],
        answers=answers,
        raw_score=scored["raw_score"],
        tolerance_level=scored["tolerance_level"],
        investment_horizon=scored["investment_horizon"],
    )
    db.add(assessment)
    db.flush()

    profile = latest_profile(db, user_id)
    if profile is None:
        profile = RiskProfile(user_id=user_id)
        db.add(profile)

    profile.tolerance_level = scored["tolerance_level"]
    profile.investment_horizon = scored["investment_horizon"]
    profile.latest_assessment_id = assessment.id
    profile.questionnaire_version = scored["version"]
    # v1 sürümü ürün grubu üretmiyor. `.get` ile okunuyor ve gelmezse NULL
    # kalıyor -- boş listeye çevirmek "soruldu, hiçbiri uygun çıkmadı" demek
    # olurdu ve o kullanıcıya hiç sorulmadı.
    profile.product_groups = scored.get("product_groups")
    profile.updated_at = datetime.now(timezone.utc)

    db.commit()
    return profile


#: The window a snapshot records. Only this one is stored: a series mixing a
#: three-month score with a one-year one would show a jump the portfolio never
#: made, because the change would be in the question rather than the answer.
SNAPSHOT_LOOKBACK = "1Y"


def record_snapshot(
    db: Session,
    user_id: str,
    lookback: str,
    scored: Dict[str, Any],
    metrics: Dict[str, Any],
    position_count: int,
) -> Optional[RiskSnapshot]:
    """Keep today's measurement, at most once per user per day.

    Best-effort, unlike `record_assessment`: this write is a side effect of
    reading the page, not something the user asked for. Losing a day of
    history is a smaller harm than refusing to show someone their risk
    because a log row would not insert.

    Returns None when nothing was written -- a non-default window, an
    unmeasurable portfolio, today's row already present, or a failure.
    """
    if lookback != SNAPSHOT_LOOKBACK:
        return None
    if scored.get("score") is None:
        # A day with nothing to measure is not a day at zero risk. Recording
        # it would put a crash on the chart that the portfolio never had.
        return None

    today = datetime.now(timezone.utc).date()
    try:
        existing = (
            db.query(RiskSnapshot)
            .filter(RiskSnapshot.user_id == user_id, RiskSnapshot.captured_on == today)
            .first()
        )
        if existing is not None:
            return existing

        concentration = metrics.get("concentration") or {}
        drawdown = metrics.get("max_drawdown") or {}
        snapshot = RiskSnapshot(
            id=str(uuid.uuid4()),
            user_id=user_id,
            captured_on=today,
            score=scored.get("score"),
            level=scored.get("level"),
            volatility=metrics.get("volatility_annualized"),
            hhi=concentration.get("hhi"),
            max_drawdown=drawdown.get("value"),
            position_count=position_count,
        )
        db.add(snapshot)
        db.commit()
        return snapshot
    except Exception as exc:  # noqa: BLE001
        log.warning("could not record risk snapshot: %s", exc)
        db.rollback()
        return None


def snapshot_history(db: Session, user_id: str, days: int) -> list[RiskSnapshot]:
    """Snapshots for the last `days`, oldest first.

    Oldest first because that is the order a chart reads; reversing it in the
    component would put the burden on every caller.
    """
    since = datetime.now(timezone.utc).date() - timedelta(days=days)
    return (
        db.query(RiskSnapshot)
        .filter(RiskSnapshot.user_id == user_id, RiskSnapshot.captured_on >= since)
        .order_by(RiskSnapshot.captured_on.asc())
        .all()
    )
