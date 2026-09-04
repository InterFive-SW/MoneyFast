import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
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
    """
    global scheduler
    if scheduler is None:
        scheduler = AsyncIOScheduler(timezone='Europe/Istanbul')
    
    # Günlük bülten servisini sabah 10:00'da tetikle
    scheduler.add_job(
        send_daily_market_briefing_to_all,
        'cron',
        hour=10,
        minute=0,
        id='daily_market_briefing_job',
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("APScheduler başlatıldı. Günlük Piyasa Bülteni görevi her gün 10:00 (TSİ) olarak ayarlandı.")
