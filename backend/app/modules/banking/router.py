from fastapi import APIRouter

router = APIRouter(tags=["banking"])


@router.get(
    "/health",
    summary="Banking modülü sağlık durumu"
)
async def health_check():
    """
    Banking modülünün durumunu (health check) kontrol eder.
    Sistemin ayakta olup olmadığını ve doğru modüle ulaşıldığını doğrulamak için kullanılır.
    """
    return {"status": "ok", "module": "banking"}
