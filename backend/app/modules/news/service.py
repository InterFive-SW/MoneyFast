import asyncio
import logging
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.core.database import SessionLocal
from app.modules.auth.models import User
from app.modules.investment.market_service import (
    watchlist_symbols,
    holdings,
    latest_quotes
)
from app.modules.investment.models import InvestmentProduct, InstrumentFundamentals
from app.modules.market.service import portfolio_news
from app.core.email import send_daily_news_email

logger = logging.getLogger(__name__)

async def send_briefing_to_user(user_id: str) -> None:
    """
    Belirli bir kullanıcı için piyasa bültenini hazırlayıp e-posta ile gönderir.
    
    MİMARİ KARAR (DRY - Don't Repeat Yourself):
    Bu fonksiyon, çekirdek iş mantığını soyutlayarak hem "İsteğe Bağlı (On-Demand)" 
    HTTP API uç noktası tarafından tetiklenebilir hem de arka planda çalışan 
    "Günlük (Cron) Scheduler" tarafından toplu işlemler esnasında kullanılabilir.
    
    Veri Kesişimi ve Optimizasyon (Set/Filter):
    Kullanıcının portföyündeki varlıklar ile izleme listesindeki varlıklar arasında 
    kesişim olabilir. E-postada veri tekrarını (duplication) engellemek adına, 
    portföyde bulunan varlıklar izleme listesinden filtrelenir.
    """
    try:
        # 1. Kendi yaşam döngüsü için veritabanı bağlantısı aç
        with SessionLocal() as db:
            user = db.query(User).filter(User.id == user_id).first()
            if not user or not user.is_active:
                logger.warning(f"Bülten gönderimi iptal edildi: Kullanıcı bulunamadı veya inaktif ({user_id})")
                return
            
            # 2. Portföy (Holdings) ve İzleme Listesi (Watchlist) Verilerini Çekme
            user_holdings = holdings(db, user_id=user_id)
            user_watchlist = watchlist_symbols(db, user_id=user_id)
            
            # Portföydeki sembollerin kümesini (Set) oluştur (Hızlı arama ve filtreleme için)
            holding_symbols = {item["symbol"] for item in user_holdings} if user_holdings else set()
            
            # 3. Veri Kesişimi (Intersection Filtering) - Portföyde olanları izleme listesinden çıkar
            filtered_watchlist = [symbol for symbol in user_watchlist if symbol not in holding_symbols]
            
            # 4. Boş Kontrolü (Guard Clause)
            # Eğer kullanıcının ne portföyünde bir varlığı ne de izleme listesinde takip ettiği bir varlık yoksa erken çıkış yap.
            if not holding_symbols and not filtered_watchlist:
                logger.info("Kullanıcının portföyü ve izleme listesi boş. Gönderim iptal edildi.")
                return
            
            # Hedef varlık havuzunu birleştir (Benzersiz semboller)
            target_symbols = list(holding_symbols.union(set(filtered_watchlist)))
            
            # 5. Güncel Fiyatları Çekme
            # Haber olsun ya da olmasın, tüm hedef varlıkların son kapanış/anlık fiyatları ve değişim oranları (quotes) alınır.
            quotes = latest_quotes(db, symbols=target_symbols)
            
            # 6. Endüstri Bazlı Haber Genişletmesi (Performans Optimizasyonlu)
            # MİMARİ KARAR: Kullanıcının sadece kendi hisselerine değil, o hisselerin bulunduğu
            # endüstrideki diğer tüm gelişmelere de hakim olması istenir.
            # Performans Kuralı: Subquery (alt sorgu) kullanılarak veritabanına gidiş-dönüş 
            # sayısı (round-trip) azaltılmış ve Python seviyesinde devasa listeler tutmaktan 
            # kaçınılmıştır. Sadece ilgili endüstrilere sahip semboller tek sorguda elde edilir.
            expanded_symbols = set(target_symbols)
            if target_symbols:
                # Önce hedeflenen sembollerin endüstrilerini bul (Distinct ile tekilleştirilmiş)
                industry_query = (
                    db.query(InstrumentFundamentals.industry)
                    .join(InvestmentProduct, InstrumentFundamentals.product_id == InvestmentProduct.id)
                    .filter(InvestmentProduct.symbol.in_(target_symbols))
                    .filter(InstrumentFundamentals.industry.isnot(None))
                    .distinct()
                )
                user_industries = [row[0] for row in industry_query.all()]
                
                # Eğer kullanıcının hisselerine ait tanımlı endüstriler varsa, bu endüstrilere
                # ait tüm hisseleri (sembolleri) veritabanından çek.
                if user_industries:
                    industry_symbols_query = (
                        db.query(InvestmentProduct.symbol)
                        .join(InstrumentFundamentals, InvestmentProduct.id == InstrumentFundamentals.product_id)
                        .filter(InstrumentFundamentals.industry.in_(user_industries))
                    )
                    industry_symbols = [row[0] for row in industry_symbols_query.all()]
                    expanded_symbols.update(industry_symbols)
            
            # 7. Son 24 saate (1 gün) ait haberleri sorgula
            # Kural gereği limit=15 olarak zorunlu tutulmuştur. Email kırpılmalarını önlemek 
            # ve kullanıcının odağını dağıtmamak için en güncel 15 haber getirilir.
            news_items, _ = portfolio_news(db, list(expanded_symbols), limit=15, days=1)
            
            # Fallback to general news has been removed because it fetches completely unrelated news (e.g., regional fish catches).
            # The email template will naturally handle the empty state with a "No new developments" message.
            
            # NOT: Artık "haber yoksa iptal et" mantığı KALDIRILMIŞTIR. 
            # Haber olmasa dahi portföy ve izleme listesi özeti kullanıcıya gönderilecektir.

            # 7. Bülteni Asenkron Gönder
            await send_daily_news_email(
                email_to=user.email,
                first_name=user.first_name,
                news_items=news_items,
                holdings_data=user_holdings,
                watchlist_symbols=filtered_watchlist,
                quotes=quotes
            )
            logger.info(f"Piyasa bülteni gönderildi. (User: {user_id}, News Count: {len(news_items)}, Holdings: {len(holding_symbols)}, Watchlist: {len(filtered_watchlist)})")
            
    except Exception as e:
        logger.error(f"Kullanıcıya bülten gönderilirken hata oluştu ({user_id}): {str(e)}")


async def send_daily_market_briefing_to_all() -> None:
    """
    Günlük olarak saat 10:00'da APScheduler tarafından tetiklenen toplu bülten görevi.
    
    KVKK/GDPR UYUMU:
    Sisteme kayıtlı her aktif kullanıcının 'notification_preferences' JSONB 
    alanındaki 'daily_news -> email' ayarına bakılır. Eğer ayar bulunmazsa 
    veya 'False' ise gönderim yapılmaz. Kullanıcı rızası esastır.
    
    ALTYAPI KORUMASI (Rate Limiting):
    SMTP sunucusunda yığılmayı engellemek (Rate Limit aşımından kaçınmak) 
    amacıyla her bir e-posta gönderimi arasına 1 saniye gecikme (sleep) konulmuştur.
    """
    logger.info("Günlük piyasa bülteni toplu gönderim görevi başlatıldı.")
    
    try:
        with SessionLocal() as db:
            # Sadece aktif kullanıcıları çek
            active_users = db.query(User).filter(User.is_active == True).all()
            
            sent_count = 0
            for user in active_users:
                # KVKK Kontrolü: Bildirim tercihleri JSONB üzerinden parse edilir
                prefs = user.notification_preferences or {}
                # Eğer "market" veya "daily_news" objesi yoksa ya da içindeki "email" değeri False ise atla
                market_email = prefs.get("market", {}).get("email", False)
                daily_news_email = prefs.get("daily_news", {}).get("email", False)
                
                if not (market_email or daily_news_email):
                    logger.debug(f"Kullanıcı {user.email} için e-posta gönderimi kapalı. (Prefs: {prefs})")
                    continue
                
                # Bülten gönderim çekirdeği (DRY)
                await send_briefing_to_user(user.id)
                sent_count += 1
                
                # Rate-Limit koruması: Her gönderim arasında 1 saniye bekle
                await asyncio.sleep(1)
                
            logger.info(f"Günlük piyasa bülteni görevi tamamlandı. Toplam gönderilen: {sent_count}")
    
    except Exception as e:
        logger.error(f"Toplu bülten gönderimi esnasında sistem hatası oluştu: {str(e)}")
