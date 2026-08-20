from fastapi import APIRouter

router = APIRouter(tags=["notification"])


@router.get(
    "/health",
    summary="Notification modülü sağlık durumu"
)
async def health_check():
    """
    Notification modülünün durumunu (health check) kontrol eder.
    Sistemin ayakta olup olmadığını ve doğru modüle ulaşıldığını doğrulamak için kullanılır.
    """
    return {"status": "ok", "module": "notification"}
