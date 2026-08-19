import asyncio
import uuid
import time
from fastapi import APIRouter
from .schemas import ChatRequest, ChatResponse, WidgetData

router = APIRouter(tags=["AI Assistant"])

@router.post("/chat", response_model=ChatResponse)
async def chat_with_ai(request: ChatRequest):
    # Simulate a small network delay to make it feel like AI processing
    await asyncio.sleep(1.5)
    
    msg_id = str(uuid.uuid4())
    lower_text = request.text.lower()
    
    thoughts = [
        "Kullanıcı talebi analiz ediliyor...",
        "Canlı piyasa verileri çekiliyor...",
        "Risk modeli güncelleniyor...",
        "Yanıt oluşturuluyor..."
    ]

    response_text = "Anlaşıldı. Talebiniz üzerine standart bir analiz gerçekleştirdim. Finansal hedeflerinize uygun ilerliyorsunuz."
    context_topic = None
    widget = None

    # 1. Öncelik: Emir oluşturma niyetini (Intent) algılama
    # Kullanıcı açıkça "al", "sat", "alım", "satım", "emir" gibi kelimeler kullanıyorsa
    # RAG (grafik/haber) yerine doğrudan işlem widget'ı döndürülmelidir.
    if ("al " in lower_text or "alım" in lower_text or "sat " in lower_text or "satım" in lower_text or "emir" in lower_text) and ("aapl" in lower_text or "apple" in lower_text):
        context_topic = "AAPL İşlem"
        action_type = "buy" if ("al " in lower_text or "alım" in lower_text) else "sell"
        action_tr = "Alım" if action_type == "buy" else "Satım"
        
        # Basit bir miktar çıkarma mantığı (gelişmiş bir NLP yerine basit arama)
        import re
        amount_match = re.search(r'(\d+)\s*(lot|adet)?', lower_text)
        amount = int(amount_match.group(1)) if amount_match else 10

        response_text = f"Anlaşıldı. AAPL hissesi için {amount} lot {action_tr} emri hazırlıyorum. İşlemi onaylıyor musunuz?"
        
        widget = WidgetData(
            type="action",
            payload={
                "message": f"{amount} Lot AAPL {action_tr} Emri",
                "confirmLabel": "Evet, Onayla",
                "cancelLabel": "İptal",
                "actionId": f"order_{action_type}_aapl",
                "asset": "AAPL",
                "action": action_type,
                "amount": amount
            }
        )
    
    # 2. Öncelik: Sektörel veya genel portföy analizi
    elif "portföy" in lower_text or "risk" in lower_text:
        context_topic = "Portföy"
        response_text = "Portföyünüzün ağırlıklı kısmı Teknoloji sektöründe bulunuyor. BIST 100 endeksindeki son dalgalanmaları göz önüne alarak, teknoloji ağırlığını %10 azaltıp temettü verimi yüksek sanayi hisselerine yönelmenizi tavsiye edebilirim. İşlemi hazırlamamı ister misiniz?"
        widget = WidgetData(
            type="action",
            payload={
                "message": "Portföy dengeleme: %10 Teknoloji sat, %10 Sanayi al.",
                "confirmLabel": "Evet, İşlemi Hazırla",
                "cancelLabel": "Vazgeç",
                "actionId": "rebalance_10"
            }
        )
        
    # 3. Öncelik: Hisse bilgisi ve grafik (Eğer alım/satım niyeti yoksa sadece bilgi ver)
    elif "apple" in lower_text or "aapl" in lower_text:
        context_topic = "AAPL"
        response_text = "Apple (AAPL) son çeyrekte donanım satışlarında %3'lük bir daralma yaşasa da servis gelirlerinde rekor kırdı. Analistlerin kısa vadeli hedef fiyatı $210 seviyesinde. Son 5 günlük fiyat değişimi grafiğini aşağıda bulabilirsiniz."
        widget = WidgetData(
            type="chart",
            payload={
                "title": "AAPL Son 5 Günlük Performans",
                "color": "#0ea5e9",
                "data": [
                    {"name": "Pzt", "value": 185},
                    {"name": "Sal", "value": 182},
                    {"name": "Çar", "value": 188},
                    {"name": "Per", "value": 191},
                    {"name": "Cum", "value": 189}
                ]
            }
        )
    elif "thyao" in lower_text or "sasa" in lower_text or "bist" in lower_text:
        context_topic = "BIST 100"
        response_text = "Bugün BIST 100 endeksi günü dalgalı geçirdi. THYAO ve SASA gibi lokomotif hisselerin hacim artışı dikkat çekiyor. Aşağıda genel durumu görebilirsiniz."
        widget = WidgetData(
            type="chart",
            payload={
                "title": "BIST 100 Gün İçi Performans",
                "color": "#10b981",
                "data": [
                    {"name": "10:00", "value": 9800},
                    {"name": "12:00", "value": 9950},
                    {"name": "14:00", "value": 9870},
                    {"name": "16:00", "value": 10050},
                    {"name": "18:00", "value": 10120}
                ]
            }
        )
    
    return ChatResponse(
        id=msg_id,
        text=response_text,
        context_topic=context_topic,
        widget=widget,
        thoughts=thoughts
    )


@router.get(
    "/health",
    summary="Ai_assistant modülü sağlık durumu"
)
async def health_check():
    """
    Ai_assistant modülünün durumunu (health check) kontrol eder.
    Sistemin ayakta olup olmadığını ve doğru modüle ulaşıldığını doğrulamak için kullanılır.
    """
    return {"status": "ok", "module": "ai_assistant"}
