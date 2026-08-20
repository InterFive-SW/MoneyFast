from fastapi import APIRouter, HTTPException

from . import rules, service
from .schemas import ComplianceRequest, ComplianceResponse

router = APIRouter(tags=["compliance"])


@router.post(
    "/validate",
    response_model=ComplianceResponse,
    summary="Yanıt taslağını mevzuat kurallarına göre denetle (MCP v2.1 sözleşmesi)",
)
async def validate_compliance(request: ComplianceRequest):
    """
    Kullanıcıya gönderilmeden önce yanıt taslağını denetler.

    Deterministik kural paketi; LLM kullanmaz. Bu kapı, dil modelinin ürettiği
    metni denetlemek için var — aynı sağlayıcıya bağımlı olsaydı, sağlayıcı
    çöktüğünde kontrol de sessizce devre dışı kalırdı.

    Tek bir CRITICAL bulgu doğrudan BLOCK üretir. Güvenli bir düzeltmesi
    olmayan bulgular da BLOCK üretir; orijinal taslak hiçbir koşulda geri
    dönüş değeri değildir.
    """
    try:
        return service.validate(request.model_dump())
    except service.UnsupportedJurisdiction as exc:
        # 400 maps to InvalidInputError in the MCP client, which the
        # orchestrator converts to BLOCK. Failing closed on an unknown rule
        # pack is the whole point.
        raise HTTPException(
            status_code=400,
            detail=(
                f"Desteklenmeyen yetki alanı: {exc}. "
                f"Desteklenenler: {', '.join(sorted(rules.SUPPORTED_JURISDICTIONS))}"
            ),
        )


@router.get("/health", summary="Compliance modülü sağlık durumu")
async def health_check():
    return {"status": "ok", "module": "compliance"}
