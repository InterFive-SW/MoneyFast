from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.modules.investment import models, schemas
import logging

logger = logging.getLogger(__name__)

def process_order_confirmation(db: Session, current_user: dict, request: schemas.OrderConfirmRequest) -> dict:
    """
    Kullanıcı tarafından onaylanan siparişi veritabanına işler, 
    bakiye kontrolü yapar ve sipariş sonucunu döner.
    """
    # 1. Kullanıcı ID'sini auth modülünün (simüle edilmiş) çıktısından güvenli bir şekilde al
    user_id = current_user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Geçersiz kullanıcı oturumu.")
        
    try:
        # 2. Kullanıcının portföyünü veritabanından çek (Portfolio Check)
        portfolio = db.query(models.Portfolio).filter(models.Portfolio.user_id == user_id).first()
        
        # Eğer portföy yoksa, varsayılan 100.000 sanal bakiye ile oluştur (Test/Geliştirme için)
        if not portfolio:
            logger.info(f"Portföy bulunamadı, {user_id} için 100.000 sanal bakiye tanımlanıyor.")
            portfolio = models.Portfolio(user_id=user_id, balance=100000.0, currency="TRY")
            db.add(portfolio)
            db.flush() # ID almak için flush yapıyoruz
            
        # 3. Tutar Hesabı
        # Şimdilik hisse anlık fiyatı dinamik çekilemediği için sembolik olarak 300 kabul ediyoruz
        mock_stock_price = 300.0
        total_cost = request.amount * mock_stock_price
        
        if request.action == "buy":
            # 4. Bakiye kontrolü
            if portfolio.balance < total_cost:
                logger.warning(f"Yetersiz bakiye. İstenen: {total_cost}, Mevcut: {portfolio.balance}")
                raise HTTPException(
                    status_code=400, 
                    detail=f"Yetersiz bakiye. İşlem tutarı: {total_cost} {portfolio.currency}, Mevcut bakiyeniz: {portfolio.balance} {portfolio.currency}"
                )
            
            # Bakiyeden düş
            portfolio.balance -= total_cost
        elif request.action == "sell":
            # Satış işlemi için bakiyeye ekle (Burada hisse adedi kontrolü de yapılmalı ancak görev kapsamında istenmedi)
            portfolio.balance += total_cost
        else:
            raise HTTPException(status_code=400, detail="Geçersiz işlem türü. (Sadece 'buy' veya 'sell')")
            
        # 5. Sipariş (OrderTransaction) Kaydı
        new_order = models.OrderTransaction(
            user_id=user_id,
            asset_symbol=request.asset,
            action=request.action,
            amount=request.amount,
            total_price=total_cost,
            status="COMPLETED"
        )
        db.add(new_order)
        
        # 6. Tüm işlemleri kalıcı hale getir (Transaction Commit)
        db.commit()
        
        logger.info(f"Kullanıcı {user_id} için {request.amount} lot {request.asset} {request.action} emri başarıyla tamamlandı.")
        
        return {
            "message": f"Sipariş başarıyla onaylandı (Sipariş No: {new_order.id})",
            "status": "confirmed",
            "total_cost": total_cost,
            "new_balance": portfolio.balance
        }
        
    except HTTPException:
        # HTTPException fırlatılmışsa, yakalayıp logla ve tekrar fırlat (Zaten 400 dönecek)
        db.rollback()
        raise
    except Exception as e:
        # Beklenmedik bir hata olursa veritabanı tutarlılığını korumak için rollback yap
        db.rollback()
        logger.error(f"Sipariş işlenirken beklenmeyen hata oluştu: {str(e)}")
        raise HTTPException(status_code=500, detail="İşlem sırasında sunucu hatası oluştu.")

