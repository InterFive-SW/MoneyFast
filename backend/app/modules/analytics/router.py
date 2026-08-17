from fastapi import APIRouter

router = APIRouter(tags=["analytics"])


@router.get(
    "/health",
    summary="Analytics modülü sağlık durumu"
)
async def health_check():
    """
    Analytics modülünün durumunu (health check) kontrol eder.
    Sistemin ayakta olup olmadığını ve doğru modüle ulaşıldığını doğrulamak için kullanılır.
    """
    return {"status": "ok", "module": "analytics"}
