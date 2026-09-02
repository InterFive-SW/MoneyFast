from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import desc
from uuid import UUID

from app.core.database import get_db
from app.core.deps import get_current_user
from app.modules.auth.models import User
from app.modules.notification.models import Notification
from app.modules.notification.schemas import NotificationListResponse, NotificationResponse

router = APIRouter(tags=["notification"])


@router.get(
    "/me/notifications",
    response_model=NotificationListResponse,
    summary="Kullanıcının bildirimlerini getirir"
)
async def get_my_notifications(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Sisteme giriş yapmış kullanıcının bildirimlerini sayfalandırılmamış (fakat limitli) olarak döner.
    Polling stratejisi kullanıldığı için her 30 saniyede bir çağrılır. En yeni bildirimler en üstte yer alır.
    Ayrıca okunmamış bildirim sayısını hesaplayarak frontend üzerindeki badge güncellemesi için döner.
    """
    # İlgili kullanıcının en yeni bildirimlerini (limitli olarak) getiriyoruz
    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(desc(Notification.created_at))
        .limit(limit)
        .all()
    )
    
    # Okunmamış (badge count) bildirimlerin sayısını tüm kayıtlar üzerinden (limite takılmadan) alıyoruz
    unread_count = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read == False)
        .count()
    )
    
    return NotificationListResponse(
        unread_count=unread_count,
        items=notifications
    )


@router.put(
    "/me/notifications/{notification_id}/read",
    response_model=NotificationResponse,
    summary="Belirli bir bildirimi okundu olarak işaretler"
)
async def mark_notification_as_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Kullanıcı arayüzünde belirli bir bildirime tıklandığında (veya üzerine gelindiğinde),
    bildirimin `is_read` (okundu) bayrağını True yapar.
    Sadece ilgili kullanıcının kendi bildirimine müdahale etmesine izin verilir (Authorization Check).
    """
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .first()
    )
    
    if not notification:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Bildirim bulunamadı veya bu bildirimi güncelleme yetkiniz yok."
        )
        
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    
    return notification


@router.post(
    "/me/notifications/mark-all-read",
    summary="Tüm bildirimleri okundu olarak işaretler"
)
async def mark_all_notifications_as_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Kullanıcının okunmamış tüm bildirimlerini tek seferde (batch update) okundu olarak işaretler.
    Bu işlem genellikle 'Tümünü Okundu İşaretle' butonuna basıldığında tetiklenir ve sayaç (badge) sıfırlanır.
    """
    db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False
    ).update({"is_read": True})
    
    db.commit()
    
    return {"message": "Tüm bildirimler okundu olarak işaretlendi."}
