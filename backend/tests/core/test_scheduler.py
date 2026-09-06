"""Zamanlanmış işlerin kurulumu ve YAŞAM DÖNGÜSÜ.

Buradaki asıl iddia ikinci çağrıyla ilgili. `AsyncIOScheduler` başlatıldığı
andaki event loop'a bağlanıyor ve `shutdown()`dan sonra o referansı
bırakmıyor; modül seviyesindeki nesne yeniden kullanıldığında ikinci bir
yaşam döngüsünde `add_job` kapanmış loop'a `call_soon_threadsafe` deniyor ve
`RuntimeError: Event loop is closed` fırlatıyordu.

Ölçülen sonuç bir tek testin hatası değildi: paket içinde `TestClient(app)`
açan ilk testten SONRAKİ her test kurulum aşamasında hata veriyordu.
"""

from __future__ import annotations

import pytest

from app.core import scheduler as scheduler_module


#: Testler ASENKRON. `AsyncIOScheduler` başlarken `get_event_loop()`
#: çağırıyor ve çalışan bir loop yoksa Python 3.12'de bu artık
#: `RuntimeError: There is no current event loop`. Senkron çalıştıklarında
#: paket sırasına göre bazen geçip bazen düşüyorlardı -- sırası testi
#: belirleyen bir iddia, iddia değildir.
pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _clean_scheduler():
    scheduler_module.stop_scheduler()
    yield
    scheduler_module.stop_scheduler()


class TestJobsRegistered:
    async def test_both_jobs_are_scheduled(self):
        scheduler_module.start_scheduler()
        ids = {job.id for job in scheduler_module.scheduler.get_jobs()}
        assert ids == {"daily_market_briefing_job", "limit_order_matching_job"}

    async def test_the_briefing_runs_on_istanbul_time(self):
        """Container UTC'de; 10:00 TSİ demek için saat dilimi açıkça
        verilmeli."""
        scheduler_module.start_scheduler()
        assert str(scheduler_module.scheduler.timezone) == "Europe/Istanbul"

    async def test_matching_does_not_overlap_itself(self):
        """İki tur aynı bekleyen emri okuyup iki kez doldurabilirdi."""
        scheduler_module.start_scheduler()
        job = scheduler_module.scheduler.get_job("limit_order_matching_job")
        assert job.max_instances == 1
        assert job.coalesce is True


class TestLifecycle:
    async def test_starting_twice_does_not_raise(self):
        """Asıl hata buydu: ikinci yaşam döngüsü kapanmış bir loop'a iş
        eklemeye çalışıyordu."""
        scheduler_module.start_scheduler()
        first = scheduler_module.scheduler
        scheduler_module.start_scheduler()
        assert scheduler_module.scheduler is not first
        assert len(scheduler_module.scheduler.get_jobs()) == 2

    async def test_stopping_releases_the_reference(self):
        scheduler_module.start_scheduler()
        scheduler_module.stop_scheduler()
        assert scheduler_module.scheduler is None

    async def test_stopping_when_never_started_is_a_no_op(self):
        scheduler_module.stop_scheduler()
        assert scheduler_module.scheduler is None

    async def test_a_failing_shutdown_is_logged_rather_than_raised(self, mocker, caplog):
        """Kapanış yolu birden fazla kez çalışabiliyor; istisnayı dışarı
        vermek uygulamanın kapanışını hatayla bitirirdi."""
        scheduler_module.start_scheduler()
        mocker.patch.object(
            scheduler_module.scheduler, "shutdown", side_effect=RuntimeError("boom")
        )
        with caplog.at_level("WARNING"):
            scheduler_module.stop_scheduler()
        assert scheduler_module.scheduler is None
        assert "boom" in caplog.text
