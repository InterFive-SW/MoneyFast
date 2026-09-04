from fastapi import APIRouter, BackgroundTasks, Depends
from starlette.responses import JSONResponse
from app.core.deps import get_current_user_id
from app.modules.news.service import send_briefing_to_user

# Otomatik yönlendirme mekanizması için APIRouter instance'ı
# prefix belirtmiyoruz, main.py otomatik olarak '/api/news' ekleyecektir.
router = APIRouter(tags=["news"])

@router.post("/me/market-briefing/send-now", status_code=202)
async def send_market_briefing_now(
    background_tasks: BackgroundTasks,
    current_user_id: str = Depends(get_current_user_id)
):
    """
    Kullanıcının isteği üzerine (On-Demand) piyasa bültenini anında tetikler.
    
    MİMARİ KARAR (BackgroundTasks):
    Veritabanı sorguları (watchlist + haberler) ve SMTP üzerinden e-posta gönderimi 
    I/O bloklayan (blocking) ağır işlemlerdir. Bu uç nokta (endpoint), kullanıcıyı
    bekletmemek ve "Hızlı Yanıt" (Fast Response) sağlamak adına `BackgroundTasks` 
    altyapısını kullanır. İşlem arkaya atılır atılmaz 202 Accepted dönülür.
    
    NOT: Bu istek kullanıcı tarafından bilinçli olarak (On-Demand) yapıldığı için 
    KVKK/GDPR 'Günlük Bülten' izin ayarı (daily_news.email) pas geçilir.
    """
    
    # Arka plan görevini (Background Task) kuyruğa ekle
    background_tasks.add_task(send_briefing_to_user, current_user_id)
    
    # İstemciye (Frontend) anında yanıt dön
    return JSONResponse(
        status_code=202,
        content={"message": "Bülten hazırlanıp e-posta adresinize gönderiliyor."}
    )
