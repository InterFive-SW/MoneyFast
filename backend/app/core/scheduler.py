import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.modules.investment.matching import match_open_orders_job
from app.modules.news.service import send_daily_market_briefing_to_all

logger = logging.getLogger(__name__)

# Global olarak tanımlıyoruz, ancak event loop uyuşmazlığını (uvloop vb.)
# önlemek için `start_scheduler` içinde, yani FastAPI yaşam döngüsü
# (lifespan) başladıktan sonra başlatacağız.
scheduler = None


def start_scheduler():
    """
    Uygulama ayağa kalktığında zamanlanmış görevleri (Cron Jobs) kurar ve başlatır.

    MİMARİ KARAR (Saat Dilimi Sabitleme):
    Docker konteynerleri genellikle UTC zaman diliminde çalışır. Türkiye'deki
    kullanıcılara sabah 10:00'da bülten gitmesi için scheduler'a spesifik
    'Europe/Istanbul' timezone'u verilmiş ve CronTrigger kullanılmıştır.

    HER ÇAĞRIDA YENİ bir scheduler kuruluyor, mevcut olan yeniden
    kullanılmıyor. `AsyncIOScheduler` başlatıldığı andaki event loop'a
    bağlanıyor ve kapatıldıktan sonra o referansı bırakmıyor; ikinci bir
    yaşam döngüsünde `add_job` o ölü loop'a `call_soon_threadsafe` deniyor ve
    `RuntimeError: Event loop is closed` fırlatıyordu. Ölçülen sonuç: paket
    içinde `TestClient(app)` açan İLK testten sonraki her test kurulum
    aşamasında hata veriyordu (yüzlerce ERROR satırı).
    """
    global scheduler
    stop_scheduler()
    scheduler = AsyncIOScheduler(timezone="Europe/Istanbul")

    # Günlük bülten servisini sabah 10:00'da tetikle
    scheduler.add_job(
        send_daily_market_briefing_to_all,
        "cron",
        hour=10,
        minute=0,
        id="daily_market_briefing_job",
        replace_existing=True,
    )

    # Bekleyen limit emirlerini eşleştir.
    #
    # Dakikada bir: fiyat akışı 30 saniyede bir yazıyor, dolayısıyla daha sık
    # taramak aynı kotasyonu iki kez okumak olurdu. Aralık, emrin ne kadar
    # geç dolabileceğinin de üst sınırı -- bu yüzden "günde bir" değil.
    #
    # Fonlar aynı iş içinde ama tabiatı gereği günde bir kez ilerliyor: NAV
    # günde bir yayımlanıyor, dolayısıyla aradaki turlarda fon emirleri
    # değişmemiş bir fiyatı görüp atlanıyor.
    scheduler.add_job(
        match_open_orders_job,
        "interval",
        minutes=1,
        id="limit_order_matching_job",
        # Bir tur uzarsa ikincisi ÜST ÜSTE binmemeli: iki tur aynı emri
        # okuyup iki kez doldurabilirdi.
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "APScheduler başlatıldı. Günlük Piyasa Bülteni 10:00 (TSİ); "
        "emir eşleştirme dakikada bir."
    )


def stop_scheduler():
    """Çalışan scheduler'ı durdurur ve referansı BIRAKIR.

    Referansı bırakmak asıl mesele: `shutdown()` çağrılmış bir scheduler
    nesnesi hâlâ kapanmış event loop'u tutuyor ve bir sonraki yaşam
    döngüsünde yeniden kullanılırsa iş eklenemiyor.

    Durmuş bir scheduler'ı durdurmak hata DEĞİL: kapanış yolu birden fazla
    kez çalışabiliyor ve `SchedulerNotRunningError`i dışarı vermek,
    uygulamanın kapanışını bir istisnayla bitirirdi.
    """
    global scheduler
    if scheduler is None:
        return
    try:
        scheduler.shutdown(wait=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Scheduler kapatılamadı: %s", exc)
    scheduler = None
