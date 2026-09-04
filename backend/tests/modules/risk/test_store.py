"""Risk profilinin kalıcılığı.

`ai_orchestrator.service.record_turn`'den ayrılan tek nokta burada: o
best-effort, çünkü cevap zaten üretilmiş ve log satırını kaybetmek daha küçük
bir zarar. Burada yazma İŞLEMİN KENDİSİ — sessizce düşen bir anket, kullanıcıyı
beyan etmediği bir toleransı beyan ettiğine inandırır.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy.orm import Session

from app.modules.risk import store

SCORED = {
    "version": "v1",
    "raw_score": 52.5,
    "tolerance_level": "Orta",
    "investment_horizon": "3-5 yıl",
}
ANSWERS = {"horizon": "3_5y", "goal": "balanced"}


def make_db(existing_profile=None) -> MagicMock:
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.first.return_value = existing_profile
    return db


class TestLatestProfile:
    def test_returns_the_row_when_there_is_one(self):
        profile = SimpleNamespace(user_id="u1")
        assert store.latest_profile(make_db(profile), "u1") is profile

    def test_returns_none_before_the_questionnaire_is_taken(self):
        assert store.latest_profile(make_db(None), "u1") is None


class TestRecordAssessment:
    def test_a_first_submission_writes_both_rows(self):
        """Değerlendirme geçmişi ve geçerli profil birlikte doğar."""
        db = make_db(None)
        store.record_assessment(db, "u1", ANSWERS, SCORED)
        assert db.add.call_count == 2
        assert db.commit.called

    def test_the_assessment_keeps_the_raw_answers(self):
        """Bir puanlama değişikliği, sonucuna değil söylenene karşı
        denetlenebilmeli."""
        db = make_db(None)
        store.record_assessment(db, "u1", ANSWERS, SCORED)
        assessment = db.add.call_args_list[0].args[0]
        assert assessment.answers == ANSWERS
        assert assessment.raw_score == 52.5
        assert assessment.questionnaire_version == "v1"

    def test_the_assessment_id_exists_before_the_profile_needs_it(self):
        """Kolon varsayılanı yalnızca flush anında uygulanır; profil satırı
        id'yi ondan önce istiyor."""
        db = make_db(None)
        profile = store.record_assessment(db, "u1", ANSWERS, SCORED)
        assessment = db.add.call_args_list[0].args[0]
        assert assessment.id
        assert profile.latest_assessment_id == assessment.id

    def test_a_second_submission_updates_the_existing_profile(self):
        """Tolerans değişikliği yeni bir profil satırı doğurmaz: aynı kişi
        için iki cevap, hangisinin kullanıldığını belirsiz bırakırdı."""
        existing = SimpleNamespace(
            user_id="u1", tolerance_level="Düşük", investment_horizon="1-3 yıl",
            latest_assessment_id="eski", questionnaire_version="v1", updated_at=None,
        )
        db = make_db(existing)
        profile = store.record_assessment(db, "u1", ANSWERS, SCORED)
        # Yalnızca değerlendirme eklendi; profil güncellendi.
        assert db.add.call_count == 1
        assert profile is existing
        assert existing.tolerance_level == "Orta"
        assert existing.latest_assessment_id != "eski"
        assert existing.updated_at is not None

    def test_the_horizon_travels_with_the_profile(self):
        db = make_db(None)
        profile = store.record_assessment(db, "u1", ANSWERS, SCORED)
        assert profile.investment_horizon == "3-5 yıl"


# --------------------------------------------------------------------------
# Faz 4: risk geçmişi
# --------------------------------------------------------------------------
SNAP_SCORED = {"score": 83.4, "level": "Düşük"}
SNAP_METRICS = {
    "volatility_annualized": 0.18,
    "concentration": {"hhi": 0.16},
    "max_drawdown": {"value": -0.11},
}


def make_snapshot_db(existing=None) -> MagicMock:
    db = MagicMock(spec=Session)
    db.query.return_value.filter.return_value.first.return_value = existing
    return db


class TestRecordSnapshot:
    def test_the_default_window_is_recorded(self):
        db = make_snapshot_db()
        snapshot = store.record_snapshot(db, "u1", "1Y", SNAP_SCORED, SNAP_METRICS, 14)
        assert snapshot is not None
        assert snapshot.score == 83.4
        assert snapshot.volatility == 0.18
        assert snapshot.hhi == 0.16
        assert snapshot.max_drawdown == -0.11
        assert snapshot.position_count == 14
        assert db.commit.called

    def test_a_non_default_window_is_not_recorded(self):
        """Üç aylık bir puanla bir yıllık puanı aynı seride toplamak,
        portföyün hiç yapmadığı bir sıçrama gösterir: değişen cevap değil,
        soru olurdu."""
        db = make_snapshot_db()
        assert store.record_snapshot(db, "u1", "3M", SNAP_SCORED, SNAP_METRICS, 14) is None
        assert db.add.called is False

    def test_an_unmeasurable_day_is_not_recorded_as_zero(self):
        """Ölçülemeyen bir gün, riski sıfır olan bir gün değil. Kaydetmek
        grafiğe portföyün hiç yaşamadığı bir çöküş çizerdi."""
        db = make_snapshot_db()
        assert store.record_snapshot(db, "u1", "1Y", {"score": None}, {}, 0) is None
        assert db.add.called is False

    def test_the_second_read_of_the_day_reuses_the_first_row(self):
        """Günde bir satır kısıtı şemada; kod yolu unutulsa bile tablo
        kullanıcı başına yılda ~365 satırla sınırlı kalır."""
        from types import SimpleNamespace

        existing = SimpleNamespace(id="snap-1", score=83.4)
        db = make_snapshot_db(existing)
        assert store.record_snapshot(db, "u1", "1Y", SNAP_SCORED, SNAP_METRICS, 14) is existing
        assert db.add.called is False

    def test_a_failure_does_not_cost_the_user_their_risk_page(self):
        """`record_assessment`'in aksine bu best-effort: sayfayı okumanın yan
        etkisi, kullanıcının istediği bir işlem değil."""
        db = make_snapshot_db()
        db.commit.side_effect = RuntimeError("connection reset")
        assert store.record_snapshot(db, "u1", "1Y", SNAP_SCORED, SNAP_METRICS, 14) is None
        assert db.rollback.called

    def test_missing_metric_blocks_yield_none_not_zero(self):
        db = make_snapshot_db()
        snapshot = store.record_snapshot(db, "u1", "1Y", SNAP_SCORED, {}, 3)
        assert snapshot.volatility is None
        assert snapshot.hhi is None
        assert snapshot.max_drawdown is None


class TestSnapshotHistory:
    def test_it_asks_for_the_window_and_orders_oldest_first(self):
        db = MagicMock(spec=Session)
        chain = db.query.return_value.filter.return_value.order_by.return_value
        chain.all.return_value = ["a", "b"]
        assert store.snapshot_history(db, "u1", 90) == ["a", "b"]
        assert db.query.return_value.filter.return_value.order_by.called
