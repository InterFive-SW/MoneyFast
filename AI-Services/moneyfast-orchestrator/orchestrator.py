"""MoneyFast LangGraph orchestrator.

Graph shape:

    START
      -> router_node                 (safety pre-filter, then Groq routing)
      -> one of:
           portfolio_node            (get_portfolio_positions)
           market_data_node          (get_market_data)
           market_research_node      (rag_semantic_market_search)
           risk_node                 (positions, then risk metrics)
           transaction_node          (prepare_transaction_proposal, staging)
           handoff_node              (unsafe / distress, no tools)
           synthesis_node            (education, smalltalk, clarification)
      -> synthesis_node              (Turkish markdown draft)
      -> compliance_gate_node        (validate_compliance_rules)
      -> synthesis_node on BLOCK, up to MAX_COMPLIANCE_REVISIONS
      -> END

Fail-closed is the invariant: if compliance cannot run, or still blocks after
the revision budget, the user gets the compliance-supplied refusal text and
never the draft.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
from functools import lru_cache
from typing import Any, Literal, NamedTuple, Optional, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

import agent_trace
import sources
from mcp_client import MCPToolError, MCPUnavailable, get_mcp_client
from prompts import (
    ORCHESTRATOR_SYSTEM_PROMPT,
    REVISION_TASK_TEMPLATE,
    ROUTER_PROMPT,
    ROUTER_TASK_TEMPLATE,
    SPECIALIST_PROMPTS,
    SYNTHESIS_TASK_TEMPLATE,
)

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("moneyfast.graph")

JURISDICTION = os.getenv("JURISDICTION", "TR")
DEFAULT_LOCALE = os.getenv("DEFAULT_LOCALE", "tr-TR")
MAX_COMPLIANCE_REVISIONS = int(os.getenv("MAX_COMPLIANCE_REVISIONS", "1"))

#: The context window's safety net, NOT its authority.
#:
#: The backend decides how much conversation the model sees
#: (`ai_orchestrator.service.trim_history`, 20 messages / 7500 characters) and
#: applies it to both the stored and the client-supplied path. These numbers
#: are deliberately LOOSER, which makes them provably inert behind the
#: backend -- 8000 clears 7500 plus the role prefixes -- while still bounding
#: the CLI and anyone calling this service directly.
#:
#: Do not "fix the inconsistency" by making them equal. Equal numbers put two
#: live trimmers in the path and the next person to widen the window would
#: have to find both.
HISTORY_MAX_TURNS = int(os.getenv("HISTORY_MAX_TURNS", "20"))
#: 8.000'di ve `SYNTHESIS_PAYLOAD_CHARS`'ın aritmetiğiyle ÇELİŞİYORDU. O
#: hesap geçmiş için ~1.500 token ayırıyor; 8.000 karakter ise ~2.000 token
#: eder. Üç tavan aynı anda dolduğunda toplam 8.475 token çıkıyor ve
#: sağlayıcının tek istek sınırı 8.000.
#:
#: Ölçüldü, uzun bir sohbette: gövde bütçesine SIĞDIĞI hâlde istek 8.871
#: token oldu ve kullanıcı "tek seferde işleyebileceğimden büyük çıktı"
#: cevabı aldı. Tavan yazılı varsayıma çekildi -- 6.000 karakter ≈ 1.500
#: token, ve 4.475 + 1.500 + 2.000 = 7.975.
HISTORY_MAX_CHARS = int(os.getenv("HISTORY_MAX_CHARS", "6000"))

#: How much of a PREVIOUS ANSWER survives into the prompt. Only the subject
#: is needed to resolve "ondan 2 adet"; the body is what a model copies when
#: it should be reading this turn's tool payload instead.
HISTORY_ANSWER_EXCERPT_CHARS = int(os.getenv("HISTORY_ANSWER_EXCERPT_CHARS", "220"))

GENERIC_FAILURE_TR = (
    "Şu anda yanıtı hazırlayamadım. Kısa bir süre sonra tekrar deneyebilir "
    "misiniz?"
)

#: Rate limiting deserves its own sentence. Under the generic message a
#: quota exhaustion looked identical to a broken application: four turns in a
#: row, including "selam", answered "Şu anda yanıtı hazırlayamadım" with
#: nothing telling the user that waiting is the fix.
RATE_LIMITED_TR = (
    "Şu anda yoğunluk sınırına takıldım ve yanıt üretemiyorum. Bu geçici bir "
    "durum — birkaç dakika sonra tekrar denerseniz kaldığımız yerden devam "
    "ederiz."
)

#: İstek, modelin tek seferde alabileceğinden BÜYÜK. Sağlayıcı bunu 413 ile
#: ve `rate_limit_exceeded` koduyla döndürüyor, dolayısıyla aşağıdaki kota
#: işaretlerine de takılıyor -- ama ikisi karşıt durumlar: kota beklemekle
#: geçer, bu geçmez. Bir dakika sonra aynı istek yine aynı boyutta.
#:
#: ÖLÇÜLDÜ ve kullanıcı bildirdi: "faizler artarsa portföyüm nasıl etkilenir"
#: her seferinde "yoğunluk sınırına takıldım, birkaç dakika sonra deneyin"
#: cevabı veriyordu; aynı oturumda sorulan başka sorular anında cevaplanıyordu.
#: Beklemek hiçbir zaman işe yaramayacaktı. Sağlayıcı kaydı: 8.393 token
#: istendi, sınır 8.000.
_TOO_LARGE_MARKERS = (
    "request too large", "reduce your message size", "413",
    "context length", "maximum context",
)

#: Yapılandırma hatası: model adı artık geçerli değil. Kotadan da boyuttan
#: da farklı, çünkü BEKLEMEK düzeltmiyor ve isteği daraltmak da düzeltmiyor
#: -- düzeltecek olan tek şey `LLM_PROVIDER`/`*_MODEL` ayarını değiştirmek.
#:
#: ÖLÇÜLDÜ, ve tam da bu yüzden var: NVIDIA NIM'e geçerken belgelerin
#: önerdiği iki model adı da bir hafta önce emekliye ayrılmıştı ve uç nokta
#: `410 Gone` döndü: "The model 'meta/llama-3.3-70b-instruct' has reached its
#: end of life on 2026-08-26". Kullanıcı "kısa bir süre sonra tekrar
#: deneyin" cevabı aldı; bekleyerek geçmeyecek bir şey için.
#:
#: Adlar dar tutuldu. Çıplak "404" YOK: bir jeton sayısında ya da bir istek
#: kimliğinde geçebilir ve kalıcı olmayan bir hatayı kalıcı diye anlatmak,
#: bu dosyanın zaten bir kez düzelttiği hatanın aynadaki hâli olurdu.
_CONFIG_ERROR_MARKERS = (
    "end of life", "no longer available", "model_not_found",
    "does not exist", "410",
)

MISCONFIGURED_TR = (
    "Yapılandırılmış dil modeli şu anda kullanılamıyor, bu yüzden yanıt "
    "üretemedim. Bu geçici bir yoğunluk değil: beklemek düzeltmez, ayarın "
    "güncellenmesi gerekiyor."
)

#: Substrings that mark a provider quota/rate-limit refusal. Matched on the
#: exception text because the LLM client wraps the provider's 429 rather than
#: raising a typed error.
_RATE_LIMIT_MARKERS = ("rate limit", "rate_limit", "429", "quota", "too many requests")

#: Geçici taşıma hataları. Kota gibi bunlar da bir sonraki denemede
#: geçebiliyor; kalıcı bir yapılandırma hatası (eksik anahtar) geçmiyor ve
#: bu yüzden burada yok.
_TRANSPORT_MARKERS = ("timeout", "timed out", "connection", "temporarily", "503", "502")

#: Boyut hatası kullanıcıya beklemesini SÖYLEMEZ. Beklemek düzeltmiyor ve
#: "birkaç dakika sonra deneyin" demek, kullanıcıyı hiç sonuçlanmayacak bir
#: döngüde tutmak olur -- kullanıcı bunu bizden önce fark etti.
TOO_LARGE_TR = (
    "Bu sorunun yanıtı için toplanan veri tek seferde işleyebileceğimden "
    "büyük çıktı, bu yüzden yanıtı hazırlayamadım. Beklemek bunu değiştirmez; "
    "soruyu daha dar sorarsanız (örneğin tek bir konuya odaklanarak) "
    "yanıtlayabilirim."
)


def _failure_message(exc: Exception) -> str:
    """Sağlayıcı hatasını kullanıcıya doğru cümleyle anlatır.

    Boyut kontrolü kota kontrolünden ÖNCE: Groq'un 413'ü `rate_limit_exceeded`
    kodunu taşıyor ve sıra ters olsaydı kalıcı bir hata geçici diye
    anlatılırdı -- ki tam olarak bu oldu.
    """
    text = str(exc).casefold()
    if any(m in text for m in _TOO_LARGE_MARKERS):
        return TOO_LARGE_TR
    if any(m in text for m in _CONFIG_ERROR_MARKERS):
        return MISCONFIGURED_TR
    return RATE_LIMITED_TR if any(m in text for m in _RATE_LIMIT_MARKERS) else GENERIC_FAILURE_TR


#: Transaction types the backend recognises as money transfers. The tool
#: docstring once documented TRANSFER_INTERNAL/EXTERNAL, which the backend
#: rejects — the three the backend accepts are the contract.
TRANSFER_TYPES = frozenset({"TRANSFER", "EFT", "HAVALE"})

DATA_FAILURE_TR = (
    "Verilere şu anda ulaşamadım, bu yüzden sayı paylaşmayacağım. "
    "Birazdan tekrar denememi ister misiniz?"
)

AGENTS = [
    "PORTFOLIO_AGENT",
    "MARKET_DATA_AGENT",
    "MARKET_RESEARCH_AGENT",
    "RISK_STRATEGY_AGENT",
    "TRANSACTION_AGENT",
    "EDUCATION_AGENT",
    "SMALLTALK_AGENT",
    "HUMAN_HANDOFF",
]


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------
class MoneyFastState(TypedDict, total=False):
    # Required by the architecture spec
    user_message: str
    conversation_history: list[dict[str, str]]
    primary_intent: str
    target_agent: str
    specialist_output: dict[str, Any]
    draft_response: str
    compliance_verdict: str
    final_output: str
    #: Required notices, carried separately so the UI can place them.
    disclosures: list[str]
    #: Crisis resources for a distress turn. Set by the handoff node and
    #: merged into `disclosures` on EVERY compliance branch, including BLOCK.
    #: Left to the model these appeared about half the time; a safety control
    #: that depends on a sampled token is not a control.
    crisis_notices: list[str]
    # Operational
    user_id: str
    locale: str
    entities: dict[str, Any]
    #: Bu turda adı geçen ya da önceki turlardan taşınan enstrüman.
    #: `entities` her turda bilerek sıfırlanıyor (bkz. `_initial_state`), o
    #: yüzden "kap verilerine göre nasıl" gibi bir devam sorusunda hisse
    #: adı yalnızca 220 karaktere kırpılmış düzyazı özette kalıyordu.
    carried_ticker: Optional[str]
    #: Bu tur bir ARAMA değil, önceki turun kaynağına dair bir soru mu.
    meta_request: Optional[str]
    #: Turda birden çok ayrı istek varsa, her birinin kendi başına ayakta
    #: duran hâli ve o istek için seçilen ajan. Boş liste = tek istek.
    #: Yönlendirici TEK çağrıda üretiyor, `compound` düğümü tüketiyor.
    sub_requests: list[dict[str, str]]
    safety_flags: list[str]
    needs_clarification: bool
    clarifying_question: Optional[str]
    tools_used: list[str]
    compliance: dict[str, Any]
    blocked_reason: Optional[str]
    revision_count: int
    errors: list[str]


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
class Provider(NamedTuple):
    """Bir sağlayıcının uç noktası, anahtar adı ve model adları."""

    base_url: str
    api_key_env: str
    model_env: str
    default_model: str
    fast_env: str
    default_fast: str
    #: Sağlayıcıya özel gövde alanları. Boş bırakılabilir.
    extra_body: dict = {}


#: Desteklenen sağlayıcılar. Üçü de OpenAI-uyumlu `/chat/completions`
#: konuşuyor, dolayısıyla tek istemci hepsini kapsıyor.
#:
#: **Model adları sağlayıcıya ÖZEL, ortak bir `LLM_MODEL` yok.**
#: `llama-3.3-70b-versatile` ile `meta/llama-3.3-70b-instruct` birbirinin
#: yerine geçen dizgeler değil; tek bir ortak değişken, sağlayıcı
#: değiştirildiğinde yanlış id göndermek ve anlaşılmaz bir 404 almak demekti.
PROVIDERS = {
    "groq": Provider(
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        model_env="GROQ_MODEL", default_model="llama-3.3-70b-versatile",
        fast_env="GROQ_FAST_MODEL", default_fast="llama-3.1-8b-instant",
    ),
    "nvidia": Provider(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key_env="NVIDIA_API_KEY",
        # ADLAR ÖLÇÜLEREK SEÇİLDİ, belgeden kopyalanmadı. Belgelerin ve
        # üçüncü taraf rehberlerin önerdiği `meta/llama-3.3-70b-instruct` ve
        # `meta/llama-3.1-8b-instruct` 2026-08-26'da emekliye ayrılmış ve uç
        # nokta `410 Gone` dönüyor. Katalogda görünen adların çoğu da bu
        # hesapta 404: listelenmek, sunulmak demek değil.
        model_env="NVIDIA_MODEL", default_model="nvidia/nemotron-3-super-120b-a12b",
        fast_env="NVIDIA_FAST_MODEL", default_fast="nvidia/nemotron-3.5-lightning-30b-a3b",
        # NIM'in nemotron-3 ailesi AKIL YÜRÜTEN modeller: varsayılan olarak
        # düşünme adımlarını `content` alanına yazıyorlar ("Okay, the user is
        # asking..."). O hâliyle yönlendirme JSON'u ayrıştırılamaz ve sentez
        # çıktısı kullanıcıya modelin düşüncesini gösterirdi. Kapatınca
        # temiz JSON dönüyor -- ölçüldü.
        extra_body={"chat_template_kwargs": {"thinking": False}},
    ),
    "openai": Provider(
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        model_env="OPENAI_MODEL", default_model="gpt-4o",
        fast_env="OPENAI_FAST_MODEL", default_fast="gpt-4o-mini",
    ),
}

DEFAULT_PROVIDER = "groq"


def provider_name() -> str:
    return os.getenv("LLM_PROVIDER", DEFAULT_PROVIDER).strip().lower()


def provider() -> Provider:
    """Yapılandırılmış sağlayıcı.

    Tanınmayan bir ad HATA veriyor, ve bu `embeddings.prefixes()`'ten
    BİLEREK farklı. Orada bilinmeyen bir model güvenli varsayılana düşüyor,
    çünkü yanlış bir önek recall'a mal olur ve eksik önek hiçbir şeye. Burada
    güvenli bir varsayılan YOK: operatör `nvida` yazdığında Groq'a düşmek,
    NVIDIA model adlarını Groq'a göndermek demek.
    """
    name = provider_name()
    found = PROVIDERS.get(name)
    if found is None:
        raise RuntimeError(
            f"LLM_PROVIDER={name!r} is not a known provider; "
            f"choose one of {', '.join(sorted(PROVIDERS))}"
        )
    return found


def model_name(fast: bool = False) -> str:
    """Bu turda kullanılacak model adı. İSTEMCİ KURMUYOR.

    `/readyz` bunu okuyor: istemci kurmak, hazırlık yoklamasını anahtarın
    varlığına bağlar ve eksik bir anahtar MCP erişilebilirliğini raporlamak
    için yazılmış bir ucu 503'e çevirirdi.
    """
    entry = provider()
    return (
        os.getenv(entry.fast_env, entry.default_fast) if fast
        else os.getenv(entry.model_env, entry.default_model)
    )


@lru_cache(maxsize=2)
def get_llm(fast: bool = False):
    """Lazy so importing this module never requires a key.

    `lru_cache` TAŞIYICI: `tests/conftest.py`'deki autouse fixture
    `get_llm.cache_clear()` çağırıyor. Dekoratör kalkarsa süitteki her test
    kurulum aşamasında hata verir.
    """
    from langchain_openai import ChatOpenAI

    entry = provider()
    # Ortak ad önce: compose'da tek bir korumalı değişken var ve sağlayıcıya
    # özel ad, geliştiricinin kendi `.env`'i için geriye dönük kapı.
    api_key = os.getenv("LLM_API_KEY") or os.getenv(entry.api_key_env)
    if not api_key:
        raise RuntimeError(
            f"{entry.api_key_env} is not set (LLM_PROVIDER={provider_name()})"
        )
    return ChatOpenAI(
        model=model_name(fast),
        temperature=0,
        api_key=api_key,
        base_url=entry.base_url,
        extra_body=dict(entry.extra_body) or None,
    )


#: Kota hatasında kaç kez yeniden denenir. Dakikalık pencere uygulayan bir
#: sağlayıcıda birkaç saniyelik bekleme çoğu turu kurtarıyor.
LLM_MAX_ATTEMPTS = int(os.getenv("LLM_MAX_ATTEMPTS", "3"))

#: İlk bekleme, saniye. Sonrakiler ikiye katlanıyor.
#:
#: 1,5 saniye GROQ'un penceresine karşı ölçüldü; NVIDIA NIM için yeniden
#: ölçülmedi. Sağlayıcı `Retry-After` döndürüyorsa onu okumak tahmin
#: etmekten iyidir -- yapılmadı, ve yapılana kadar bu bir varsayım.
LLM_BACKOFF_SECONDS = float(os.getenv("LLM_BACKOFF_SECONDS", "1.5"))


async def _llm_text(system: str, user: str, fast: bool = False) -> str:
    """Modele giden TEK yol -- `_llm_json` de buradan geçiyor.

    Yeniden deneme YALNIZCA kota/taşıma hatasında. Bozuk JSON'da değil:
    sıcaklık sıfır, yani aynı istem aynı baytları döndürür ve yeniden
    denemek sağlayıcıya bedava bir yük bindirmekten başka bir şey yapmaz.

    Buraya kadar hiçbir yerde yeniden deneme yoktu ve sonucu ölçüldü:
    tek bir 429, kullanıcıya "yoğunluk sınırına takıldım" olarak döndü ve
    tur orada bitti.
    """
    llm = get_llm(fast)
    messages = [SystemMessage(content=system), HumanMessage(content=user)]
    delay = LLM_BACKOFF_SECONDS
    for attempt in range(1, LLM_MAX_ATTEMPTS + 1):
        try:
            reply = await llm.ainvoke(messages)
            return (reply.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            if attempt >= LLM_MAX_ATTEMPTS or not _is_retryable(exc):
                raise
            log.warning(
                "llm attempt %d/%d failed (%s), retrying in %.1fs",
                attempt, LLM_MAX_ATTEMPTS, exc, delay,
            )
            await asyncio.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")  # pragma: no cover


def _is_retryable(exc: Exception) -> bool:
    """Yeniden denemeye değer bir hata mı.

    `_failure_message` ile aynı metin eşlemesi, aynı sebeple: istemci
    sağlayıcının 429'unu sarmalıyor ve tipli bir hata fırlatmıyor.

    **Boyut kontrolü ÖNCE, ve `_failure_message` ile aynı sırada.**
    Sağlayıcının 413'ü `rate_limit_exceeded` kodunu taşıyor ve gövdesinde
    "Requested 8429, Limit 8000" gibi bir sayı geçiyor -- `_RATE_LIMIT_MARKERS`
    içindeki çıplak "429" ona takılıyor. O koruma olmadan kalıcı bir hata üç
    kez deneniyor: 4,5 saniye bekleme ve sağlayıcıya bedava üç istek, hepsi
    aynı sonuçla.

    Sınır: yalnızca "Requested 8429" yazan, hiçbir boyut işareti taşımayan
    bir gövde hâlâ yeniden denenir. Koruma `413` / `request too large` /
    `context length` gibi bir işaretin bulunmasına dayanıyor.
    """
    text = str(exc).casefold()
    if any(marker in text for marker in _TOO_LARGE_MARKERS + _CONFIG_ERROR_MARKERS):
        return False
    return any(marker in text for marker in _RATE_LIMIT_MARKERS + _TRANSPORT_MARKERS)


async def _llm_json(system: str, user: str, fast: bool = False) -> dict[str, Any]:
    raw = await _llm_text(system, user, fast=fast)
    return _parse_json(raw)


def _parse_json(raw: str) -> dict[str, Any]:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```")[1] if "```" in text[3:] else text[3:]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        log.warning("llm returned no json object: %.160s", raw)
        return {}
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        log.warning("llm returned malformed json: %.160s", raw)
        return {}
    return parsed if isinstance(parsed, dict) else {}


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------
#: Bu sistemin ölçemediği makro faktörler. Sabit var, seri yok:
#: `TR_POLICY_RATE` tek bir sayı ve enflasyon hiç toplanmıyor. Liste dar
#: tutuldu -- ölçülebilen faktörler (dolar, euro, BIST, altın) BURAYA GİRMEZ,
#: onların yolu zaten doğru çalışıyor.
_UNMEASURABLE_FACTOR = re.compile(
    r"\b(faiz|faizler|faizin|faizi|enflasyon|enflasyonun|tüfe|tufe|ppk)\b",
    re.IGNORECASE,
)

#: Turun kullanıcının KENDİ portföyü hakkında olduğunu gösteren sözcükler.
#: İkisi birden gerekiyor: "faiz nedir" bir tanım sorusu ve EDUCATION_AGENT'ın
#: işi; "faizler artarsa portföyüm ne olur" bir ölçüm talebi.
_OWNERSHIP_WORD = re.compile(
    r"\b(portföy\w*|portfoy\w*|pozisyon\w*|hissem|hisselerim\w*|"
    r"yatırımlarım\w*|yatirimlarim\w*|varlığım\w*|varligim\w*)\b",
    re.IGNORECASE,
)


def _is_unmeasurable_factor_turn(message: str) -> bool:
    """Ölçülemeyen bir makro faktör + kullanıcının KENDİ portföyü.

    İkisi birden gerekiyor: "faiz nedir" bir tanım sorusu, "faizler artarsa
    portföyüm ne olur" bir ölçüm talebi ve ölçüm yapılamaz.
    """
    return bool(
        _UNMEASURABLE_FACTOR.search(message) and _OWNERSHIP_WORD.search(message)
    )


def _forced_agent(message: str) -> Optional[str]:
    """Ölçülemeyen bir makro faktör + kullanıcının kendi portföyü.

    Kodda, çünkü ÖLÇÜLDÜ: "faizler artarsa portföyüm nasıl etkilenir" iki ayrı
    denemede de EDUCATION_AGENT'a gitti -- yönlendirme kuralı prompt'a
    yazıldıktan SONRA da. Bu modülün kendi dersi (`_keep_crisis`,
    `_verify_named_instrument`): prompt tavsiyedir ve zorunlu bir davranışın
    kodda bir karşılığı olmalı.

    Yanlış cevabın iki ayrı zararı vardı: "veriler alınamadı" bir KESİNTİ gibi
    okunuyordu -- oysa faiz serisi yapısal olarak yok, "şu anda" değil hiçbir
    zaman -- ve kullanıcıdan pozisyonlarını YAPIŞTIRMASI isteniyordu, ki bu
    ürün pozisyonları kayıt saklayıcısından okur ve MCP sözleşmesi kullanıcı
    beyanını açıkça yasaklar.

    RISK_STRATEGY_AGENT ölçemediğini biliyor ve sebebini söylüyor. Doğru cevap
    "hesaplayamıyorum" değil, "bu sistemde faiz serisi tutulmuyor".

    Güvenlik kararlarını EZMEZ: çağıran bunu DISTRESS_SIGNAL kontrolünden
    ÖNCE uyguluyor, dolayısıyla güvenlik her zaman üstte kalıyor.
    """
    return "RISK_STRATEGY_AGENT" if _is_unmeasurable_factor_turn(message) else None


async def router_node(state: MoneyFastState) -> dict[str, Any]:
    """Classify the turn, in two passes with different trust levels.

    Pass 1 is the MCP safety pre-filter: deterministic regex, no model. It
    decides distress routing on its own, because a safety gate that depends on
    the model it is guarding fails open exactly when the model misbehaves.

    Pass 2 asks the model for the topic. Its answer is accepted for routing
    only; it can add safety flags but never clear one, and it cannot override a
    non-overridable decision from pass 1.

    Failure is not fatal: an unreachable MCP server or an unparseable model
    reply both degrade to EDUCATION_AGENT, which holds no user data and can
    emit no figures. Guessing a specialist here would send an unclassified
    turn at a tool that reads someone's holdings.
    """
    safety: dict[str, Any] = {}
    errors: list[str] = []
    try:
        safety = await get_mcp_client().call(
            "classify_and_route_intent",
            {
                "user_message": state["user_message"],
                "conversation_summary": _history_summary(state),
                "available_agents": AGENTS,
                "locale": state.get("locale") or DEFAULT_LOCALE,
                "user_context_flags": {"has_linked_account": bool(state.get("user_id"))},
            },
        )
    except (MCPUnavailable, MCPToolError) as exc:
        # Losing the pre-filter is serious but not a reason to drop the turn:
        # the model is still asked, and its own safety_flags still apply.
        log.error("safety pre-filter unavailable: %s", exc)
        errors.append(f"safety_prefilter: {exc}")

    flags = list(safety.get("safety_flags") or [])

    if safety.get("is_overridable") is False:
        target = safety.get("target_agent") or "HUMAN_HANDOFF"
        log.warning("routing fixed by safety pre-filter: agent=%s flags=%s", target, flags)
        return {
            "primary_intent": safety.get("primary_intent") or "DISTRESS",
            "target_agent": target,
            "entities": {},
            "safety_flags": flags,
            "needs_clarification": False,
            "clarifying_question": None,
            "tools_used": ["classify_and_route_intent"],
            "revision_count": 0,
            "errors": errors,
        }

    try:
        result = await _llm_json(
            ROUTER_PROMPT,
            ROUTER_TASK_TEMPLATE.format(
                user_message=state["user_message"],
                conversation_summary=_history_summary(state) or "(none)",
                available_agents=", ".join(AGENTS),
                safety_flags=", ".join(flags) or "(none)",
            ),
            fast=True,
        )
    except Exception as exc:  # network, rate limit, malformed JSON
        # Kota hatasında sessizce EDUCATION_AGENT'a düşmek kendi başına bir
        # yanlış yönlendirme: kullanıcı konusuyla ilgisiz bir cevap alıyor ve
        # hiçbir yerde bir hata görünmüyor. Hata artık turla birlikte
        # taşınıyor ve sentez onu okuyabiliyor.
        log.error("router classification failed: %s", exc)
        # Deterministik kapı BU YOLDA DA geçerli -- hatta asıl burada.
        # Sınıflandırıcı düştüğünde tur EDUCATION_AGENT'a düşüyor ve o ajan
        # hiçbir araç tutmuyor; ölçüldü, sonuç "gerekli veriler alınamadı"
        # oldu ve kullanıcı bunu bir kesinti sandı. Oysa faiz serisi zaten
        # yok ve bunu söylemek için bir model çağrısına ihtiyaç yok.
        #
        # Güvenlik burada da üstte: `flags` pass 1'in deterministik regex'i
        # ve sıkıntı sinyali her şeyi eziyor.
        fallback = "EDUCATION_AGENT"
        if "DISTRESS_SIGNAL" not in flags:
            fallback = _forced_agent(state["user_message"]) or fallback
        return {
            "primary_intent": "OUT_OF_SCOPE",
            "target_agent": "HUMAN_HANDOFF" if "DISTRESS_SIGNAL" in flags else fallback,
            "sub_requests": [],
            "entities": {},
            "carried_ticker": None,
            "meta_request": None,
            "safety_flags": flags,
            "needs_clarification": False,
            "clarifying_question": None,
            "tools_used": ["classify_and_route_intent"],
            "revision_count": 0,
            "errors": errors + [f"router: {exc}"],
        }

    target = result.get("target_agent")
    if target not in AGENTS:
        # A hallucinated agent name must not fall through to a real specialist.
        log.warning("router returned unknown agent %r, falling back", target)
        target = "EDUCATION_AGENT"

    # Ölçülemeyen bir makro faktör hakkındaki portföy sorusu, reddi BİLEN
    # ajana gider. Güvenlik kontrolünden ÖNCE, ki DISTRESS_SIGNAL bunu her
    # zaman ezebilsin.
    forced = _forced_agent(state["user_message"])
    if forced is not None and target != forced:
        log.info("routing override: %s -> %s (unmeasurable factor)", target, forced)
        target = forced

    # Union, never replacement: the model may notice an injection attempt the
    # regex missed, but it may not clear a flag the regex raised.
    for flag in result.get("safety_flags") or []:
        if flag not in flags:
            flags.append(flag)
    if "DISTRESS_SIGNAL" in flags:
        target = "HUMAN_HANDOFF"

    needs_clarification = bool(result.get("needs_clarification"))
    if float(result.get("confidence") or 0) < 0.60:
        needs_clarification = True

    intent = result.get("primary_intent") or "OUT_OF_SCOPE"
    entities = result.get("entities") or {}
    tickers = entities.get("tickers") or []
    message = state["user_message"]
    reason = None

    # Bu tur bir arama değil, önceki turun kaynağına dair bir soru mu.
    # Yönlendirmeden ÖNCE bakılıyor: "bana kaynakça verir misin" araştırma
    # ajanına gitse bile, kullanıcının cümlesini arama sorgusu olarak
    # göndermek boş sonuçtan başka bir şey üretmiyor (ölçüldü).
    meta_request = None
    # Güvenlik her şeyi önceler. Aşağıdaki düzeltmelerin hiçbiri bir sıkıntı
    # turunu yönlendirmeden çıkaramaz, o yüzden hepsi bu koşulun içinde.
    if "DISTRESS_SIGNAL" not in flags:
        if _is_sources_recap(state, tickers):
            # Bu tur bir arama değil, önceki turun kaynağına dair bir soru.
            # Kullanıcının cümlesini arama sorgusu olarak göndermek boş
            # sonuçtan başka bir şey üretmiyor -- ölçüldü.
            meta_request = "SOURCES_RECAP"
            target, reason = "MARKET_RESEARCH_AGENT", "sources-recap"
        elif intent.startswith("MARKET_RESEARCH") and target == "MARKET_DATA_AGENT":
            # Yönlendiricinin kendi içinde çeliştiği durum. Ölçüldü: "kap
            # verilerine göre nasıl" sorusunda `MARKET_RESEARCH` niyeti ile
            # `MARKET_DATA_AGENT` ajanı BİRLİKTE döndü ve hiçbir yer bunu
            # uzlaştırmıyordu. Niyet zaten doğruydu; eksik olan ona göre
            # davranmaktı.
            target, reason = "MARKET_RESEARCH_AGENT", "intent-agent-mismatch"
        elif _mentions_filing(message) and target in ("MARKET_DATA_AGENT", "EDUCATION_AGENT"):
            # Belge sözcüğü geçiyorsa tur araştırmaya gider. Piyasa verisi
            # ajanının derleme hiçbir yolu yok; oraya düşen bir tur
            # bildirimi ASLA göremez.
            target, reason = "MARKET_RESEARCH_AGENT", "filing-keyword"

        if reason:
            log.info(
                "router override (%s): %s -> %s",
                reason, result.get("target_agent"), target,
            )

    carried = tickers[0] if tickers else _ticker_from_history(state)

    log.info(
        "routed intent=%s agent=%s confidence=%s flags=%s ticker=%s",
        intent, target, result.get("confidence"), flags, carried,
    )
    # Bileşiklik yalnızca GERÇEKTEN birden çok istek varsa taşınıyor:
    # `is_compound` true ama tek alt istek dönen bir sınıflandırma, turu
    # gereksiz yere ikinci bir yönlendirmeden geçirirdi.
    sub_requests = (
        _parse_sub_requests(result.get("sub_requests"))
        if result.get("is_compound")
        else []
    )
    if len(sub_requests) < 2:
        sub_requests = []

    return {
        "primary_intent": intent,
        "target_agent": target,
        "entities": entities,
        "carried_ticker": carried,
        "meta_request": meta_request,
        "sub_requests": sub_requests,
        "safety_flags": flags,
        "needs_clarification": needs_clarification,
        "clarifying_question": result.get("clarifying_question"),
        "tools_used": ["classify_and_route_intent"],
        "revision_count": 0,
        "errors": errors,
    }


async def portfolio_node(state: MoneyFastState) -> dict[str, Any]:
    plan = await _llm_json(
        SPECIALIST_PROMPTS["PORTFOLIO_AGENT"], _specialist_task(state), fast=True
    )
    args = plan.get("arguments") or {}
    args["user_id"] = state.get("user_id") or "unknown"

    # Two tools behind one agent, the same split as MARKET_DATA_AGENT: what
    # the user OWNS, and what was PUBLISHED about it. The intersection lives
    # here rather than in market research because it is not a search --
    # "portföyümdeki hisselerle ilgili haber" names no company, so a document
    # search has nothing to search for, and only this agent can read the
    # holdings that make the question answerable.
    if plan.get("tool") == "get_portfolio_news":
        return await _run_tool(
            state, "get_portfolio_news",
            {key: args[key] for key in ("user_id", "limit", "days") if key in args},
            assumptions=plan.get("assumptions") or [],
            # An empty article list is a COMPLETE answer -- nothing matched in
            # the window -- but it must be reported with the window, so the
            # payload still travels.
            empty_when=lambda p: not p.get("articles"),
        )

    # Haberin KENDİSİ değil, ne anlama geldiği. Ayrı bir araç çünkü ayrı bir
    # dayanak: yukarıdaki başlıkları taşıyor, bu bir modelin okumasını. Aynı
    # ajanda duruyor çünkü ikisi de kullanıcının pozisyonlarının kesişimi.
    if plan.get("tool") == "get_news_impact_digest":
        return await _run_tool(
            state, "get_news_impact_digest",
            {key: args[key] for key in ("user_id", "hours") if key in args},
            assumptions=plan.get("assumptions") or [],
            # Boş bir liste TAM bir cevap -- pencerede yorumlanmış haber yok --
            # ama penceresiyle birlikte söylenmeli, o yüzden yük yine gidiyor.
            empty_when=lambda p: not p.get("entries"),
        )

    # Üçüncü araç: neye SAHİP olduğu değil, ne KAZANIP ne HARCADIĞI. Aynı
    # ajanda duruyor çünkü köprü burada kuruluyor -- "bu alımı kaldırabilir
    # miyim" sorusu hem pozisyonları hem aylık artanı gerektiriyor ve iki
    # ayrı ajan bunu tek turda birleştiremez.
    # Dördüncü araç: TEK TEK değil, hepsi birden. Diğer üçü bir soruyu
    # cevaplıyor; bu, "portföyümün genel durumu" gibi hiçbirinin tek başına
    # cevaplayamadığı soruyu.
    if plan.get("tool") == "get_portfolio_report":
        return await _run_tool(
            state, "get_portfolio_report", {"user_id": args["user_id"]},
            assumptions=plan.get("assumptions") or [],
            # Bölümü olmayan bir rapor EKSİK değil, üretilememiş demektir --
            # veri yoksa bölüm yine geliyor ve yokluğunu kendisi söylüyor.
            empty_when=lambda p: not p.get("sections"),
        )

    # Beşinci araç: VERİLMİŞ ama henüz GERÇEKLEŞMEMİŞ emirler. Pozisyonlardan
    # ayrı bir soru ve pozisyon aracı onu cevaplayamıyor: bekleyen bir alım
    # emri bir pozisyon DEĞİL, ama parayı bloke ediyor. "Bakiyem neden az"
    # sorusunun cevabı çoğu zaman burada.
    if plan.get("tool") == "get_open_orders":
        return await _run_tool(
            state, "get_open_orders", {"user_id": args["user_id"]},
            assumptions=plan.get("assumptions") or [],
            # Boş liste TAM bir cevap: bu kişinin emri yok. Eksik sayılırsa
            # ajan "veriye ulaşamadım" der ve bu bambaşka bir şey.
        )

    if plan.get("tool") == "get_cash_flow_summary":
        return await _run_tool(
            state, "get_cash_flow_summary",
            {key: args[key] for key in ("user_id", "days") if key in args},
            assumptions=plan.get("assumptions") or [],
            # `has_data: false` EKSİK değil, tam bir cevap: sistemde bu kişiye
            # ait bankacılık kaydı yok. Boş sayılırsa ajan "veriye
            # ulaşamadım" der ve bu, kaydın olmadığını söylemekten farklı.
        )

    # Reporting currency follows the session locale, not the model. It is a
    # presentation choice, and letting the model pick means a Turkish user can
    # be shown their portfolio in USD because the plan happened to say so.
    args["base_currency"] = "USD" if (state.get("locale") or DEFAULT_LOCALE).endswith("US") else "TRY"
    args.setdefault("valuation_mode", "LAST_CLOSE")
    args.setdefault("include_closed", False)
    return await _run_tool(
        state, "get_portfolio_positions", args,
        assumptions=plan.get("assumptions") or [],
        empty_when=lambda p: not p.get("positions"),
    )


async def market_data_node(state: MoneyFastState) -> dict[str, Any]:
    """Adı geçen bir enstrüman hakkında üç soru, üç araç.

    Fiyat ("ne ediyor"), eğilim ("nasıl gidiyor") ve şirketin işi ("kârlı mı").
    Üçü de aynı ajanın arkasında, çünkü üçü de bu sistemin tuttuğu veriden
    cevaplanıyor ve yönlendiricide üçe bölmek aynı soruyu üç kez sormak olurdu.
    """
    plan = await _llm_json(
        SPECIALIST_PROMPTS["MARKET_DATA_AGENT"], _specialist_task(state), fast=True
    )
    args = plan.get("arguments") or {}
    assumptions = plan.get("assumptions") or []

    # Two tools behind one agent: what it COSTS and how it is DOING. The
    # split is here rather than in the router because both answer questions
    # about a named instrument from data this system holds -- and sending the
    # open ones ("yorumlar mısın") to the document search is what produced
    # "Akbank hakkında veri bulunamadı" for an instrument with seven hundred
    # bars of history.
    # Dördüncü araç: ölçülen kanıtların hangi yöne meylettiği.
    #
    # Araç adı YALNIZCA plandan okunmuyor ve bu ölçülmüş bir sebep: "ASELS
    # önümüzdeki 3 ayda nasıl gider" turunda planlayıcı `{"horizon": "3M",
    # "symbols": ["ASELS"]}` üretti ama aracı `get_market_data` seçti --
    # vadeyi doğru anladı, aracı yanlış. `horizon` argümanını kabul eden tek
    # araç bu, dolayısıyla onun varlığı aracın kendisini söylüyor.
    # `_SORT_SYNONYMS` ile aynı desen: prompt tavsiye, kod zorlar.
    wants_direction = (
        plan.get("tool") == "get_direction_signal" or "horizon" in args
    )
    if wants_direction:
        symbol = args.get("symbol") or _first_ticker(state)
        if not symbol:
            symbols = args.get("symbols") or []
            symbol = str(symbols[0]).upper() if symbols else None
        if symbol:
            horizon = (
                _horizon_from_message(state.get("user_message") or "")
                or str(args.get("horizon") or DEFAULT_DIRECTION_HORIZON).upper()
            )
            return await _run_tool(
                state, "get_direction_signal",
                {"symbol": str(symbol).upper(), "horizon": horizon},
                assumptions=assumptions,
                # Boş `narrative` okumanın kurulamadığını söylüyor; rakamlar
                # yine gidiyor ve ajan boşluğu bildiriyor.
                empty_when=lambda p: not p.get("narrative"),
            )

    if plan.get("tool") == "get_technical_signals":
        symbol = args.get("symbol") or _first_ticker(state)
        if symbol:
            return await _run_tool(
                state, "get_technical_signals", {"symbol": symbol},
                assumptions=assumptions,
                # `narrative` empty means the history is too short to read.
                # The figures still travel; the agent reports the gap.
                empty_when=lambda p: not p.get("narrative"),
            )
        # No symbol to look up. Falling through to the price path lets the
        # turn be answered from whatever the user did name, rather than
        # calling a one-symbol tool with nothing.

    # Üçüncü araç: şirketin İŞİ nasıl gidiyor. Fiyat "ne ediyor", eğilim
    # "nasıl gidiyor", bu ise "kârlı mı, borçlu mu". Üçü de ADI GEÇEN bir
    # enstrüman hakkında ve üçü de bu sistemin tuttuğu veriden cevaplanıyor;
    # ayrı bir uzman ajan açmak, aynı soruyu yönlendiricide üçe bölmeyi
    # gerektirirdi.
    if plan.get("tool") == "get_company_fundamentals":
        symbols = [
            str(symbol).upper()
            for symbol in (args.get("symbols") or [])
            if str(symbol).strip()
        ] or [t for t in ((state.get("entities") or {}).get("tickers") or [])]
        if symbols:
            return await _run_tool(
                state, "get_company_fundamentals",
                # Sözleşmenin tavanı beş ve aşıldığında REDDEDİYOR. Burada
                # kırpmak, aracın bilerek reddettiği şeyi sessizce yapmak
                # olurdu -- ama turu bir 422'ye çevirmek de kullanıcıya
                # kendi sorusunun cevabı yerine bir hata gösterirdi.
                # Kırpılan sembol `warnings`'e girmiyor çünkü araç onu hiç
                # görmüyor; bu yüzden model beşten fazlasını istediğinde
                # yönlendirici zaten en fazla beş ticker çıkarıyor.
                {"symbols": symbols[:5]},
                assumptions=assumptions,
                empty_when=lambda p: not p.get("instruments"),
            )
        # Sembol yoksa fiyat yoluna düşülüyor: adı geçen bir şey varsa o
        # cevaplanır, tek sembol isteyen bir aracı boşa çağırmaktansa.

    # Dördüncü araç: adı konmuş bir ÇEYREK. Diğer üçünün hiçbirinde seri
    # yok -- fiyat anlık, eğilim türetilmiş, temel veri anlık görüntü. "Son
    # çeyrek kârı" sorusunu cevaplayabilen tek yol bu.
    if plan.get("tool") == "get_quarterly_financials":
        symbol = args.get("symbol") or _first_ticker(state)
        if symbol:
            return await _run_tool(
                state, "get_quarterly_financials", {"symbol": str(symbol).upper()},
                assumptions=assumptions,
                # Boş seri, ölçülmüş bir cevap: 40 hissenin 6'sında hiç
                # çeyreklik veri yok. Hata değil.
                empty_when=lambda p: not p.get("periods"),
            )

    # A turn that named no instrument and no filter would otherwise screen the
    # entire universe and hand the model 50 rows to summarise.
    if not args.get("symbols") and not args.get("filters"):
        tickers = (state.get("entities") or {}).get("tickers") or []
        if tickers:
            args["symbols"] = tickers
    args.pop("symbol", None)
    args.setdefault("top_k", 20)
    return await _run_tool(
        state, "get_market_data", args,
        assumptions=assumptions,
        empty_when=lambda p: not p.get("instruments"),
        repair_prompt=SPECIALIST_PROMPTS["MARKET_DATA_AGENT"],
    )


#: Belge sorusu olduğunu kesinleştiren sözcükler. Bunlardan biri geçiyorsa
#: tur ARAŞTIRMA'ya gider, yönlendirici model ne derse desin.
#:
#: Neden gerekiyor: ölçüldü, "kap verilerine göre nasıl" sorusunda
#: yönlendirici `primary_intent: MARKET_RESEARCH` VE
#: `target_agent: MARKET_DATA_AGENT` döndürdü -- kendi içinde çelişen bir
#: cevap. Piyasa verisi ajanının belge derlemine hiçbir yolu yok, dolayısıyla
#: yanlış yönlendirilen bir tur bildirimi ASLA göremez.
_FILING_WORDS = (
    "kap", "bildirim", "özel durum", "açıklama", "açıkladı", "bilanço",
    "finansal rapor", "faaliyet raporu", "temettü", "kâr payı", "kar payı",
    "geri alım", "sermaye artırımı", "genel kurul",
    # "Son dönemde öne çıkan GELİŞMELER neler" -- kullanıcının sorduğu ve
    # hareketli ortalamalarla cevaplanan soru buydu. Bir gelişme sorusu
    # olup biteni sorar, fiyatın nerede olduğunu değil.
    "gelişme", "haber", "ne oldu", "neler oluyor",
)

#: Önceki turun kaynaklarını soran turlar. Bu bir arama DEĞİL.
#:
#: Liste bilerek dar. "kaynak" tek başına yok ve "kaynakları" da yok:
#: "enerji kaynakları hakkında bilgi ver" ikisine de uyuyor ve bir eğitim
#: sorusu. Kalanlar ya tek anlamlı ("kaynakça", "atıf") ya da iyelik ekiyle
#: önceki söylenene işaret ediyor ("kaynaklarını", "neye dayanarak").
_SOURCE_WORDS = ("kaynakça", "kaynakçası", "referans", "atıf",
                 "kaynağın", "kaynağını", "kaynakların", "kaynaklarını",
                 "hangi belge", "nereden ald", "neye dayanarak",
                 "link ver", "bağlantı ver")

#: Kaynağı SORMAK ile kaynağı ARAMAK'ı ayıran fiiller.
_ASK_WORDS = ("ver", "paylaş", "göster", "söyle", "misin", "mısın", "nedir", "neler")


def _mentions_filing(message: str) -> bool:
    folded = _fold(message)
    return any(_fold(word) in folded for word in _FILING_WORDS)


def _is_sources_recap(state: MoneyFastState, tickers: list) -> bool:
    """Önceki cevabın kaynağını soran bir tur mu.

    ÜÇ koşul birden aranıyor ve üçüncüsü asıl ayırıcı olan:

    1. Tek anlamlı bir kaynak sözcüğü geçiyor.
    2. Sorma fiili var -- kaynağı SORMAK ile kaynağı ARAMAK farklı şeyler.
    3. **Önceki turda gerçekten kaynak gösterilmiş.**

    Üçüncüsü olmadan "enerji kaynaklarını anlat" gibi bir eğitim sorusu bu
    yola düşüyordu; ölçüldü, testte yakalandı. Gösterilecek bir kaynak
    yoksa özetlenecek bir şey de yok, dolayısıyla tur normal yönlendirmeye
    bırakılıyor. Bu aynı zamanda güvenli tarafta başarısız oluyor: sözleşme
    henüz kaynak taşımıyorsa bu dal hiç çalışmıyor.

    Tur bir enstrüman ANIYORSA da bu bir aramadır -- "THYAO'nun kaynakları"
    aranacak bir şey söylüyor, "bana kaynakça verir misin" söylemiyor.
    """
    if tickers:
        return False
    folded = _fold(message_of(state))
    if not any(_fold(word) in folded for word in _SOURCE_WORDS):
        return False
    if not any(_fold(word) in folded for word in _ASK_WORDS):
        return False
    return bool(sources.prior(state))


def message_of(state: MoneyFastState) -> str:
    return state.get("user_message") or ""


#: Sembol biçimine uyan ama sembol OLMAYAN sözcükler. Bir BIST kodu üç ila
#: altı büyük harftir ve bu kalıba Türkçe kısaltmaların yarısı uyuyor --
#: "kap verilerine göre nasıl" sorusunda "KAP"ın kendisi dahil.
_NOT_TICKERS = frozenset({
    "KAP", "BIST", "SPK", "MKK", "ABD", "USD", "EUR", "TRY", "GBP", "TL",
    "ETF", "GYO", "AŞ", "ANO", "VYO", "IPO", "RSI", "SMA", "VAR", "PDF",
    "XLS", "CSV", "API", "SSE", "HTML", "JSON", "ISIN", "IBAN", "TCKN",
    "ODA", "DKB", "OLUR", "EVET", "HAYIR", "TAMAM", "NASIL", "NEDIR",
})

#: Bir BIST kodunun biçimi. Rakam yok: `THYAO` var ama `2026` yok.
_TICKER_SHAPE = re.compile(r"\b[A-ZÇĞİÖŞÜ]{3,6}\b")


def _ticker_from_history(state: MoneyFastState) -> Optional[str]:
    """Son kullanıcı turlarında geçen son enstrüman adayı.

    Yalnızca KULLANICI turlarına bakılıyor. Asistan turları özetlerken 220
    karaktere kırpılıyor; oradan sembol okumak, konuyu rastgele bir kesme
    noktasına bağlamak olurdu.

    Evrene karşı DOĞRULANMIYOR: orchestrator'ın enstrüman listesi yok ve
    her tur için bir tur daha atmak, çözdüğünden pahalı olurdu. Yanlış bir
    aday da sınırlı zarar veriyor -- `_narrow_then_widen` süzgeç boş
    dönünce süzgeçsiz aramaya düşüyor, yani en kötü durumda bugünkü
    davranışa geri dönülüyor. Biçime uyan ama sembol olmayan sözcükler
    (`KAP` dahil) `_NOT_TICKERS` ile eleniyor.
    """
    for turn in reversed(state.get("conversation_history") or []):
        if turn.get("role") != "user":
            continue
        for token in _TICKER_SHAPE.findall((turn.get("content") or "").upper()):
            if token not in _NOT_TICKERS:
                return token
    return None


def _first_ticker(state: MoneyFastState) -> Optional[str]:
    """The instrument this turn named, or the one carried from earlier turns."""
    tickers = (state.get("entities") or {}).get("tickers") or []
    return tickers[0] if tickers else state.get("carried_ticker")


#: Şirket adının sonundaki hukuki ekler. `symbol_match._LEGAL_SUFFIX` ile aynı
#: liste, aynı gerekçeyle: "TÜRK HAVA YOLLARI A.O." ile haberdeki "Türk Hava
#: Yolları" arasındaki tek fark bu ek. `holding` BİLEREK yok -- adın parçası
#: olduğu şirketler var ve atmak onları birbirine karıştırırdı.
_LEGAL_SUFFIXES = (" a.s.", " t.a.s.", " a.o.", " a.ş.", " t.a.ş.", " a.o")

#: Adın anlamlı sayılması için gereken en az uzunluk. Kısa bir ad parçası
#: ilgisiz metinlerde de geçiyor ve kapı bir kapı olmaktan çıkıyor.
MIN_ALIAS_LENGTH = 6


def _name_aliases(name: str) -> tuple[str, ...]:
    """Kayıtlı şirket adından, metinde aranacak biçim.

    Yalnızca hukuki ek atılıyor. Kısaltma ÜRETİLMİYOR: "Türk Hava
    Yolları"ndan "THY" türetmek bulanık eşleşmedir ve bu depo onu ölçerek
    reddetti (`symbol_match`: tek kelimelik takma adlar 1.540 haberlik bir
    derlemde eşleşmeyi 54'ten 167'ye çıkarırken `ZOREN <- "ZORLU sınavı"`
    üretiyordu). Elle yazılmış bir takma ad tablosu ayrı bir iş ve ayrı bir
    kalibrasyon gerektiriyor.
    """
    cleaned = (name or "").strip()
    folded = _fold(cleaned)
    for suffix in _LEGAL_SUFFIXES:
        if folded.endswith(_fold(suffix)):
            cleaned = cleaned[: len(cleaned) - len(suffix)].strip()
            break
    return (cleaned,) if len(cleaned) >= MIN_ALIAS_LENGTH else ()


async def _resolve_named_company(
    state: MoneyFastState,
) -> Optional[tuple[str, str]]:
    """Yönlendiricinin çıkardığı ŞİRKET ADINI sembole çevirir.

    Bu fonksiyonun yokluğu ölçülmüş bir hataya yol açtı: kullanıcı "türk hava
    yolları ne durumda yeni haberler var mı gündemde?" diye sordu ve cevapta
    kaynak olarak üç EKGYO bildirimi listelendi.

    `prompts.py` yönlendiriciden `entities.company_names` istiyor ve
    yönlendirici bunu üretiyordu -- ama orkestratörde o alanı OKUYAN tek satır
    yoktu (grep tek isabet veriyordu: istemin kendisi). "Türk Hava Yolları"
    bir ad, `_TICKER_SHAPE` ise büyük harfli 3-6 harflik dizileri arıyor,
    dolayısıyla `_first_ticker` `None` döndü, arama süzgeçsiz çalıştı ve
    ~29.000 Türkçe bildirimden 0,45 kosinüs eşiğini geçen ilk sekizi geri
    geldi.

    Çözüm ARAMA değil SÖZLÜK: "türk hava yolları" ile THYAO arasındaki bağ
    ölçülen bir benzerlik değil, kayıtlı bir gerçek. Backend'in
    `GET /market/search` ucu bunu Türkçe katlamasıyla zaten yapıyor.

    Tek bir ad çözülüyor ve yalnızca TEK bir aday döndüyse kullanılıyor: iki
    aday "benzer adlı FARKLI şirketler" demek ve birini seçmek, kullanıcının
    sormadığı şirket hakkında güvenle cevap vermek olurdu. Çözülemeyen ad
    turu DÜŞÜRMÜYOR -- süzgeçsiz arama hâlâ bir cevap, sadece daha zayıf bir
    cevap.

    Sembolün yanında ADI da dönüyor, çünkü ilgi kapısının ikisine de ihtiyacı
    var: derlemdeki bir haber şirketi koduyla değil adıyla anıyor
    ("Türk Hava Yolları'ndan yeni hamle"), ve yalnızca koda bakan bir kapı
    onu da eler.
    """
    message = _fold(state.get("user_message") or "")
    names = [
        str(name).strip()
        for name in ((state.get("entities") or {}).get("company_names") or [])
        # BU TURDA yazılmış ad. Yönlendirici önceki turun adını taşıyabiliyor:
        # ölçüldü, kullanıcı "peki aselsan için ne var?" yazdı ve
        # `company_names` hâlâ "Türk Hava Yolları" idi -- arama, sorulmayan
        # şirkete süzüldü. Zamirle devam eden bir tur (`onun haberleri`) zaten
        # `carried_ticker` üzerinden yürüyor, dolayısıyla bu kapı o yolu
        # kapatmıyor.
        if str(name).strip() and _fold(str(name)) in message
    ]
    if not names:
        return None

    result = await _run_tool(state, "resolve_instruments", {"query": names[0]})
    rows = ((result.get("specialist_output") or {}).get("data") or {}).get(
        "instruments"
    )
    if not isinstance(rows, list) or len(rows) != 1:
        log.info(
            "company name %r resolved to %d instruments; not filtering",
            names[0], len(rows) if isinstance(rows, list) else 0,
        )
        return None

    symbol = str(rows[0].get("symbol") or "").strip().upper()
    if not symbol:
        return None
    log.info("company name %r resolved to %s", names[0], symbol)
    return symbol, str(rows[0].get("name") or "")


#: Dar arama bu kadar satır bulamazsa süzgeç kaldırılıp yeniden aranır.
WIDEN_FLOOR = 3

#: Vade söylenmediğinde kullanılan okuma. Sunucudaki `signals.DEFAULT_HORIZON`
#: ile aynı ve bilerek tekrar yazılmış: ikisi ayrışırsa kullanıcı sorduğundan
#: başka bir vadenin okumasını alır ve bunu fark etmesinin bir yolu yoktur.
DEFAULT_DIRECTION_HORIZON = "3M"

#: Kullanıcının cümlesinden vade çıkarmak için desen. Rakam ve yazıyla
#: yazılmış hâller birlikte: "6 ay", "altı ayda", "3 aylık", "bir ay sonra".
_HORIZON_WORDS = {
    "1": "1M", "bir": "1M", "3": "3M", "uc": "3M", "üç": "3M",
    "6": "6M", "alti": "6M", "altı": "6M",
}
_HORIZON_RE = re.compile(
    r"\b(1|3|6|bir|[uü][cç]|alt[iı])\s*ay", re.IGNORECASE
)


def _horizon_from_message(message: str) -> Optional[str]:
    """Kullanıcının kendi yazdığı vade.

    Planlayıcının seçtiğinden ÖNCE geliyor ve sebebi ölçüldü: "THYAO
    önümüzdeki 6 ayda nasıl gider" turunda planlayıcı `horizon: "3M"`
    gönderdi. Kullanıcı altı ay sordu, üç aylık okuma aldı ve cevabın içinde
    "6 aylık tahmin için doğrudan veri bulunmamaktadır" yazıyordu -- oysa
    araç altı ayı destekliyor.

    Vade kullanıcının sorusunun bir parçası, planlayıcının bir tercihi değil;
    `_SORT_SYNONYMS` ile aynı desen -- prompt tavsiye, kod zorlar.
    """
    match = _HORIZON_RE.search(message or "")
    if not match:
        return None
    return _HORIZON_WORDS.get(match.group(1).lower())

#: Ticker süzgeçli bir aramada benzerlik tabanı. 0,45 (bkz.
#: `market_research_node`) süzgeçSİZ aramalar için ölçülmüştü: orada
#: benzerlik, belgenin konuyla ilgili olduğunu söyleyen TEK sinyal. Ticker
#: etiketi bunu doğrudan söylüyor -- etiketi taşıyan belge o şirket
#: hakkındadır -- ve puan yalnızca sıralıyor. Ölçüldü, aynı sorgu biçimiyle:
#:
#:   THYAO  "THY yılın ilk yarısında 18,86 milyar lira kar etti"  0,135
#:   ASELS  "Aselsan 125,1 milyon dolarlık satışı KAP'a bildirdi" 0,363
#:   TCELL  (aynı biçimde sorgu, aynı türden haber)                0,729
#:
#: Puan sorgunun başlıkla sözcük örtüşmesini izliyor ("THYAO" yazan sorgu,
#: "THY" yazan başlık), haberin alakasını değil. 0,45 burada uygulanınca
#: ASELS ve THYAO'nun etiketli haberlerinin TAMAMI, ticker süzgeci arşiv
#: etiketlendikten sonra bile, siliniyordu.
#:
#: Sıfır: taban süzgeç uygulandıktan sonra koruyacağı bir şeyi yok, her
#: değer gerçek sonuç kesiyor -- aynı beş THYAO haberi "THYAO hakkında
#: haber" ile 0,171, "THYAO son haberler" ile 0,014 alıyor. `top_k` ve
#: tarih sonuç kümesini zaten sınırlıyor.
TICKER_FILTERED_MIN_SIMILARITY = float(
    os.getenv("RAG_TICKER_MIN_SIMILARITY", "0.0")
)


def _research_query(state: MoneyFastState, ticker: Optional[str] = None) -> str:
    """Aramaya gidecek metin.

    Planlayıcının ürettiği sorgu KULLANILMIYOR, ve uzman istemi zaten ona
    "kullanıcının cümlesini olduğu gibi geçir, zamirleri çözme, alıcı taraf
    sunucuda çözüyor" diyordu. **O sözleşme doğru değildi.**
    `rag/app.py::_resolve_query` bağlamı yalnızca sorgunun HER kelimesi
    zamir ya da dolgu ise katıyor; "kap verilerine göre nasıl" bu koşulu
    sağlamıyor, dolayısıyla hisse adı hiç eklenmiyordu.

    Yapılan tek şey, adı geçmiyorsa taşınan sembolü BAŞA eklemek. Daha
    fazlası değil: bu depoda ölçüldü (bkz. `_fold_in_own_documents`
    yorumları), kullanıcının gerçek cümlesi kendi belgesine karşı 0,289
    alırken çıplak ölçüt 0,380 alıyor. Sorguyu "KAP bildirimi özel durum
    açıklaması son gelişmeler" gibi doldurmak benzerliği DÜŞÜRÜRDÜ.
    Daraltmak sorgunun değil süzgecin işi.
    """
    message = state["user_message"]
    ticker = ticker or _first_ticker(state)
    if not ticker or _fold(ticker) in _fold(message):
        return message
    return f"{ticker} {message}"


async def _narrow_then_widen(
    state: MoneyFastState,
    args: dict[str, Any],
    ticker: Optional[str],
    assumptions: list,
    aliases: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Önce hisseye süzülmüş, yetmezse süzgeçsiz arama.

    Neden tek başına süzgeç YANLIŞ olurdu: korpusta hisse sütunu TEK ve
    `sinks.push_disclosures_to_rag` yalnızca ilk sembolü yazıyor. İki
    şirketli bir birleşme bildiriminin ikinci şirket için bulunabilmesi,
    bilerek anlamsal aramaya bırakılmış. Sert bir süzgeç tam da onu
    kapatırdı -- ölçüldü, eşleşmelerin %37'si ikinci koddan geliyor.

    O yüzden süzgeç bir DARALTMA denemesi: yeterince satır getirirse
    kullanılır, getirmezse süzgeçsiz arama sonucu eklenir. Geniş aramanın
    başarısız olması dar sonuçları düşürmez -- `_fold_in_own_documents`
    ile aynı yön.
    """
    if not ticker:
        # Süzgeç `ticker`'dan (entity/carried_ticker'dan) gelmiyor olsa da
        # planlayıcının kendi `arguments.filters.tickers`'ı bu çağrıyı yine
        # ticker süzgeçli yapabilir; taban ona göre seçilir. `args` çağıranın
        # -- kopyası değiştirilir, kendisi değil.
        single_args = args
        if (args.get("filters") or {}).get("tickers"):
            single_args = {**args, "min_similarity": TICKER_FILTERED_MIN_SIMILARITY}
        single = await _run_tool(
            state, "rag_semantic_market_search", single_args,
            assumptions=assumptions, empty_when=lambda p: not p.get("results"),
        )
        # Bu dal da loglanıyor. Loglanmadığı sürece "hiç arama yapılmadı" ile
        # "arama yapıldı ve boş döndü" ayırt edilemiyordu ve boş dönen bir
        # tur, iz dosyası okunmadan teşhis edilemedi.
        _log_search(single_args, single, "single")
        return single

    base_filters = {k: v for k, v in (args.get("filters") or {}).items() if k != "tickers"}
    # Dar geçiş HER ZAMAN ticker süzgeçli -- kendi süzgecini burada
    # kuruyor -- dolayısıyla tabanı `args`'ın taşıdığından bağımsız olarak
    # ticker tabanına sabitlenir.
    narrow_args = {
        **args,
        "filters": {**base_filters, "tickers": [ticker]},
        "min_similarity": TICKER_FILTERED_MIN_SIMILARITY,
    }
    narrow = await _run_tool(
        state, "rag_semantic_market_search", narrow_args,
        assumptions=assumptions, empty_when=lambda p: not p.get("results"),
    )
    narrow_rows = _result_rows(narrow)
    _log_search(narrow_args, narrow, "narrow")
    if len(narrow_rows) >= WIDEN_FLOOR:
        return narrow

    # Geniş geçiş, planlayıcının koyduğu hisse süzgecini de KALDIRIYOR.
    # Kaldırmasaydı iki geçiş de aynı süzgeçle çalışır ve "geniş" hiçbir şey
    # genişletmezdi -- ölçüldü, ilk turda planlayıcı `tickers` koydu ve iki
    # geçiş de aynı sıfır sonucu döndürdü.
    wide_args = {**args, "filters": base_filters} if base_filters else {
        k: v for k, v in args.items() if k != "filters"
    }
    wide = await _run_tool(
        state, "rag_semantic_market_search", wide_args,
        assumptions=assumptions, empty_when=lambda p: not p.get("results"),
    )
    _log_search(wide_args, wide, "wide")
    # Genişletmenin amacı, hissenin `ticker` sütununda DEĞİL metninde geçtiği
    # belgeleri yakalamak -- iki şirketli bir bildirimde ikinci şirket gibi.
    # Amaç "konuyla ilgisiz haberle doldurmak" değil. Hisseyi hiç anmayan bir
    # satır bu soruya cevap değil, ve derlemede o şirkete dair bir şey yoksa
    # doğru cevap "yok" -- `results == []` zaten TAM bir cevap sayılıyor.
    wide_rows = [
        row for row in _result_rows(wide) if _is_context(row, ticker, aliases)
    ]
    if not wide_rows:
        # Dar geçiş bir şey bulduysa o. Bulmadıysa BOŞ -- `wide` DEĞİL.
        #
        # Buradan `wide` dönüyordu: hisseyi hiç anmayan satırların tamamı,
        # süzülmemiş hâliyle. Hemen üstteki yorum "hisseyi hiç anmayan bir
        # satır bu soruya cevap değil" diyor ve bu satır tam da onu geri
        # veriyordu. Uzman istemi zaten `results == []`i TAM bir cevap
        # sayıyor, dolayısıyla boş dönmenin aşağı akışta karşılığı var.
        return narrow if narrow_rows else _emptied(wide)

    seen = {row.get("chunk_id") for row in narrow_rows}
    merged = narrow_rows + [r for r in wide_rows if r.get("chunk_id") not in seen]

    output = dict((wide.get("specialist_output") or {}))
    data = dict(output.get("data") or {})
    data["results"] = merged
    output["data"] = data
    output["status"] = "OK"
    return {**wide, "specialist_output": output}


def _emptied(result: dict[str, Any]) -> dict[str, Any]:
    """Aynı zarf, sonuçları boşaltılmış hâlde.

    Zarfın kendisi korunuyor (`as_of`, `source`, tazelik alanları) çünkü arama
    GERÇEKTEN yapıldı; boş dönen şey sonuç kümesi, turun tamamı değil.
    """
    output = dict((result.get("specialist_output") or {}))
    data = dict(output.get("data") or {})
    data["results"] = []
    output["data"] = data
    return {**result, "specialist_output": output}


#: Şirketi ANMAYAN bir satırın yine de bağlam sayılması için gereken puan.
#:
#: Ölçüldü, aynı derlem ve aynı gömme modeli:
#:
#:   "petrol fiyatlari jeopolitik havayolu maliyeti"
#:     0,633  Petroldeki yükseliş ucuz uçuşları vurdu          <- makro bağlam
#:     0,623  Petrol gemileri Hürmüz Boğazı'nı geçemedi        <- makro bağlam
#:     0,622  96 dolarlık petrole THY ve Pegasus'tan hedge     <- makro bağlam
#:   "THYAO ..." (eski tur)
#:     0,463  Asya'nın en zengin ülkesinde nüfus alarmı        <- DOLGU
#:
#: Bant geniş ama iki nokta arasında; 0,55 ikisini de rahat ayırıyor.
#: Alma eşiğinden (0,45) yüksek olması kasıtlı: şirketi anmayan bir satırı
#: KAYNAK olarak listelemek, onu getirmekten daha güçlü bir iddia.
CONTEXT_MIN_SCORE = 0.55


def _is_context(row: dict[str, Any], ticker: str, aliases: tuple[str, ...]) -> bool:
    """Bu satır bu soruya bağlam sayılır mı?

    İki ayrı soru, tek bir kapıya sıkıştırılmıştı. Bir belge ya bu şirketi
    ANIYOR, ya BAŞKA bir şirketin belgesi, ya da hiçbir şirkete bağlı değil --
    ve üçüncüsü ilk ikisinden farklı davranmalı.

    * Şirketi anıyorsa: geçer (`_mentions`).
    * BAŞKA bir şirketin etiketini taşıyorsa: geçmez, puanı ne olursa olsun.
      Ölçülen hata tam buydu: THYAO sorusuna 0,669 puanlı bir EKGYO bildirimi
      kaynak gösterildi. Başka bir şirketin bildirimi bu şirket hakkında
      kanıt değildir.
    * Hiçbir etiketi yoksa: MAKRO olabilir -- petrol, faiz, jeopolitik. Bunlar
      havayolu maliyetini gerçekten açıklıyor ve hepsini elemek, kullanıcının
      istediği zinciri ("ABD saldırısı -> petrol -> THYAO") kurulamaz
      yapardı. Yalnızca daha yüksek bir puan istiyor.
    """
    if _mentions(row, ticker, aliases):
        return True
    if row.get("tickers"):
        return False
    return float(row.get("score") or 0.0) >= CONTEXT_MIN_SCORE


def _mentions(
    row: dict[str, Any], ticker: str, aliases: tuple[str, ...] = ()
) -> bool:
    """Belge bu şirketi anıyor mu -- etiketinde, kodunda ya da adıyla.

    Ad da aranıyor çünkü derlemdeki haberlerin çoğu şirketi koduyla değil
    adıyla anıyor ("Türk Hava Yolları'ndan yeni hamle"), ve yalnızca koda
    bakan bir kapı onları da elerdi -- yani ilgisiz sonuçları elerken ilgili
    olanları da.

    `aliases` yalnızca `resolve_instruments`'ın döndürdüğü KAYITLI addan
    geliyor, modelin ürettiği bir varyanttan değil: burada bulanık eşleşme
    yok, bu deponun `symbol_match` kuralıyla aynı duruş.
    """
    if ticker in (row.get("tickers") or []):
        return True
    needles = [_fold(ticker)] + [_fold(alias) for alias in aliases if alias]
    haystack = " ".join(
        _fold(str(row.get(field) or "")) for field in ("title", "snippet")
    )
    return any(needle and needle in haystack for needle in needles)


def _result_rows(result: dict[str, Any]) -> list[dict[str, Any]]:
    data = ((result.get("specialist_output") or {}).get("data") or {})
    rows = data.get("results")
    return rows if isinstance(rows, list) else []


def _log_search(args: dict[str, Any], result: dict[str, Any], pass_name: str) -> None:
    """`query_echo` bugüne kadar döndürülüp atılıyordu.

    Bu tek satır, kullanıcının "bana kaynakça verir misin" turunun neden boş
    döndüğünü sohbet kaydını okumadan görünür kılardı.
    """
    data = ((result.get("specialist_output") or {}).get("data") or {})
    log.info(
        "research %s pass: query=%r echo=%r tickers=%s results=%d",
        pass_name, args.get("query"), data.get("query_echo"),
        (args.get("filters") or {}).get("tickers"), len(_result_rows(result)),
    )


#: Korpusun belge türleri. Araç sözleşmesinde yazılı ve depoda BÜYÜK HARFLE
#: saklanıyor.
DOC_TYPES = frozenset({
    "NEWS", "ANALYST_REPORT", "FILING", "TRANSCRIPT", "MACRO_NOTE", "REGULATORY",
})


def _normalise_doc_types(filters: dict[str, Any]) -> None:
    """Planlayıcının belge türü süzgecini kullanılabilir hâle getirir.

    `languages` ile aynı arıza sınıfı, aynı sessizlik: ÖLÇÜLDÜ, planlayıcı
    `doc_types: ["news", "analysis"]` gönderdi. Depoda tür `NEWS` diye
    yazılı, dolayısıyla küçük harfli değer hiçbir satırla eşleşmiyor ve
    `analysis` zaten şemada yok. İki geçiş de sıfır döndü ve kullanıcı
    "verilere ulaşamadım" cevabı aldı -- derlemde 0,63 puanla eşleşen üç
    haber dururken.

    Büyük harfe çevriliyor (biçim hatası), tanınmayan değer DÜŞÜRÜLÜYOR ve
    loglanıyor. Hepsi düşerse süzgecin kendisi kalkıyor: geriye boş bir liste
    bırakmak "hiçbir türü kabul etme" demek olurdu, yani sessizliğin daha da
    kesini.
    """
    raw = filters.get("doc_types")
    if not raw:
        return
    wanted = [str(value).strip().upper() for value in raw]
    kept = [value for value in wanted if value in DOC_TYPES]
    dropped = [value for value in wanted if value not in DOC_TYPES]
    if dropped:
        log.info("dropping unknown doc_types %s", dropped)
    if kept:
        filters["doc_types"] = kept
    else:
        filters.pop("doc_types", None)


#: Planlayıcı sorgusunun ikinci bir deneme sayılması için gereken en az
#: uzunluk. Bir iki karakterlik "sorgu" damıtma değil, kayıp.
MIN_RETRY_QUERY_LENGTH = 8


def _is_distinct_query(planner_query: str, used_query: str) -> bool:
    """İkinci deneme yapmaya değer mi.

    Aynı metni ikinci kez aramak, aynı sıfır sonucu ikinci kez almak demek --
    ve planlayıcıya "kullanıcının cümlesini olduğu gibi geçir" dendiği için
    çoğu turda iki metin AYNI.
    """
    return (
        len(planner_query) >= MIN_RETRY_QUERY_LENGTH
        and _fold(planner_query) != _fold(used_query)
    )


async def market_research_node(state: MoneyFastState) -> dict[str, Any]:
    plan = await _llm_json(
        SPECIALIST_PROMPTS["MARKET_RESEARCH_AGENT"], _specialist_task(state), fast=True
    )
    args = plan.get("arguments") or {}
    # Planlayıcının DAMITILMIŞ sorgusu. Normal
    # yolda kullanıcının cümlesi kazanıyor (bkz. `_research_query`), ama
    # cümle uzadıkça gömme vektörü SEYRELİYOR ve hiçbir belge eşiği
    # geçemiyor.
    #
    # `arguments.query` DEĞİL, ayrı bir `fallback_query`: uzman istemi
    # planlayıcıya "kullanıcının cümlesini olduğu gibi geçir" diyor ve
    # ölçüldüğünde gerçekten öyle yapıyordu -- yani iki alan aynıydı ve
    # ikinci deneme aynı sıfır sonucu ikinci kez alıyordu. Ölçüldü:
    #
    #   "petrol fiyatları ve jeopolitik gelişmeler hakkında ne var? bu
    #    THYAO gibi havayollarını nasıl etkiler?"   -> 0 sonuç
    #   "petrol fiyatları ve jeopolitik gelişmeler" -> 0,749 / 0,719 / 0,692
    #   "petrol fiyatları havayolu maliyeti"        -> 0,640 / 0,628 / 0,602
    #
    # O 0,602'lik satır "96 dolarlık petrole THY ve Pegasus'tan hedge
    # kalkanı" -- sorunun tam cevabı derlemde duruyordu ve uzun cümle onu
    # bulunamaz kılıyordu.
    # Zarfın KÖKÜNDEN, `arguments`ın içinden değil: araç sözleşmesi donuk ve
    # oraya bilinmeyen bir alan koymak `ContractViolationError` olurdu.
    planner_query = str(plan.get("fallback_query") or "").strip()
    args.setdefault("top_k", 8)
    # Cosine thresholds are a property of the embedding model, not a product
    # constant. The tool contract documents 0.62, which is calibrated for E5;
    # the corpus is embedded with paraphrase-multilingual-MiniLM, whose scores
    # run lower, so 0.62 discarded good hits and the assistant reported "no
    # sources found" for news it was holding.
    #
    # 0.35 then overcorrected. Measured over one day of real turns:
    #
    #   "hangi bankalar ile ilgili haberer var"   0.685 .. 0.579   relevant
    #   "halkbank özelinde detaylandırır mısın"   0.577 .. 0.537   relevant
    #   "bana banka haberleri getir"              0.592 .. 0.466   relevant
    #   "hisse senedi analiz"                     0.398 .. 0.365   JUNK
    #
    # The junk band tops out below 0.40 and the worst genuine hit sits at
    # 0.466, so 0.45 separates them with room on both sides. That last query
    # returned a German bank's brothel-loan investigation and it was
    # presented to the user as stock analysis.
    #
    # Overridden here rather than in the tool, because the caller owns this
    # choice and the contract's default has to stay what it says.
    args["min_similarity"] = float(os.getenv("RAG_MIN_SIMILARITY", "0.45"))
    # Dilin ne olduğu KORPUSUN özelliği, sorunun değil -- planlayıcının
    # kararı olamaz. Süzgeç bırakılmıyor: kaldırmak "her dil" demek ve
    # derlem tek dilli olduğu sürece bir dil süzgeci yalnızca ELEYEBİLİR.
    #
    # ÖLÇÜLDÜ: planlayıcı Türkçe bir soruya `{"languages": ["en"]}` koydu ve
    # sekiz eşleşmenin tamamını sildi; kullanıcı "MIATK hakkında güncel bir
    # gelişme kaynağı bulamadım" cevabı aldı, derlemde 23 MIATK belgesi
    # dururken. `min_similarity` ile aynı gerekçe: bu seçim çağıranın.
    (args.get("filters") or {}).pop("languages", None)
    _normalise_doc_types(args.get("filters") or {})
    # The retriever scans this reversed and folds in the newest user turn it
    # finds, so the count only affects payload size, not what gets resolved.
    #
    # YALNIZCA `role` ve `content` geçiyor. Tur sözlükleri bu ikisinden
    # fazlasını taşıyor -- kaynak listesi eklendiğinden beri bir `sources`
    # DİZİSİ de var -- ve aracın şeması `dict[str, str]`. Tam turu geçirmek
    # şunu üretiyordu:
    #
    #   conversation_context.1.sources
    #     Input should be a valid string [input_value=[{'url': ...}]]
    #
    # Yani ilk kaynaklı turdan SONRAKİ her araştırma turu doğrulamada
    # düşüyordu ve kullanıcı "verilere ulaşamadım" cevabı alıyordu. Sözleşme
    # ne istiyorsa o gönderiliyor; fazlası zaten okunmuyordu.
    args["conversation_context"] = [
        {"role": str(turn.get("role") or ""), "content": str(turn.get("content") or "")}
        for turn in (state.get("conversation_history") or [])[-HISTORY_MAX_TURNS:]
    ]
    # Whose uploaded documents this search may reach, on top of the public
    # news corpus. Deliberately NOT the `"unknown"` sentinel the other nodes
    # use: that is a string, and a string that matches no user reads as a
    # narrowing filter rather than as "there is nobody here". None says the
    # second thing, which is what an anonymous turn actually is.
    args["user_id"] = state.get("user_id") or None

    # Şirket ADI varsa ÖNCE o çözülüyor, taşınan sembole bakılmadan.
    #
    # Ters sıra denendi ve yetmedi: kullanıcı "türk hava yolları ne durumda"
    # yazdığında yönlendirici `entities.tickers`e **"TÜRK"** koydu -- dört
    # büyük harf, `_TICKER_SHAPE`e uyuyor, ve hiçbir enstrümana karşılık
    # gelmiyor. `_first_ticker` onu döndürdüğü sürece ad hiç çözülmüyor ve
    # arama olmayan bir hisseye süzülüyordu (ölçüldü: `tickers=['TÜRK']`,
    # `results=0`).
    #
    # Ad, enstrüman evrenine karşı ÇÖZÜLÜYOR; modelin ürettiği bir kod ise
    # yalnızca bir tahmin. Doğrulanmış olan kazanıyor. Çözülemezse taşınan
    # sembole düşülüyor -- kullanıcı gerçekten kodu yazdıysa yolu bu.
    ticker = _first_ticker(state)
    aliases: tuple[str, ...] = ()
    resolved = await _resolve_named_company(state)
    if resolved is not None:
        ticker, name = resolved
        aliases = _name_aliases(name)

    # Sorgu, sembol ÇÖZÜLDÜKTEN sonra kuruluyor. Önce kurulduğunda
    # `_research_query` doğrulanmamış sembolü kullanıyordu ve ölçülen sonuç
    # şuydu: `query='TÜRK peki aselsan için ne var?'` -- kullanıcının hiç
    # yazmadığı bir kod, sorduğu şirketin adının önüne eklenmiş hâlde.
    args["query"] = _research_query(state, ticker)

    assumptions = plan.get("assumptions") or []
    result = await _narrow_then_widen(state, args, ticker, assumptions, aliases)

    # Hiçbir şey bulunamadıysa planlayıcının damıtılmış sorgusuyla BİR kez
    # daha. Sadece bir kez ve sadece boşken: her turda iki arama yapmak, işe
    # yarayan yolu da iki katına çıkarırdı.
    if not _result_rows(result) and _is_distinct_query(planner_query, args["query"]):
        log.info("empty research; retrying with the planner query %r", planner_query)
        retry = await _narrow_then_widen(
            state, {**args, "query": planner_query}, ticker, assumptions, aliases
        )
        if _result_rows(retry):
            result = retry

    return _slim_results(await _fold_in_own_documents(state, args, result))


#: Kullanıcının kendi belgelerine ayrılan sonuç sayısı.
#:
#: Tek bir aramada haberle YARIŞTIRMAK, yüklenen belgeyi pratikte
#: bulunamaz yapıyor. Ölçüldü: bir kullanıcı bilanço tablosu yükledi,
#: "EBITDA marjı ve hasılat" sorgusu belgeyi hiç döndürmedi; belge
#: aslında 0,605 benzerlikle eşleşiyordu ama binlerce haber parçası
#: arasında ilk yirmiye giremiyordu. Kendi yüklediği dosyayı bir daha
#: göremeyen bir yükleme özelliği, çalışmayan bir özelliktir.
OWN_DOCUMENT_SLOTS = 3

#: Yüklenen belgelerin `rag`'daki kategorisi (bkz. backend document_service).
OWN_DOCUMENT_CATEGORY = "USER_UPLOAD"

#: Kullanıcının kendi belgeleri için AYRI ve daha düşük eşik.
#:
#: 0,45 haber için doğru: binlerce parçalık bir derlemde alakasız olanı
#: elemek gerekiyor ve ölçüm o bandı gösterdi. Kişisel belgelerde elenecek
#: bir sel yok -- kullanıcının bir avuç dosyası var ve sorusu onlardan
#: birine değiniyorsa en iyi eşleşmeyi vermek neredeyse her zaman doğru.
#:
#: Ölçüldü, kullanıcının kendi yüklediği bilanço tablosuna karşı:
#:
#:   "bilançoda EBITDA marjı"                    0,390
#:   "EBITDA marjı"                              0,380
#:   "hasılat ne kadar"                          0,314
#:   "Yüklediğim bilançoda EBITDA marjı ne olmuş?" 0,289
#:
#: Sonuncusu kullanıcının GERÇEKTEN yazdığı cümle ve dolgu kelimeleri
#: gömmeyi seyreltiyor. 0,45 hepsini eliyordu: kullanıcı dosyayı yükledi,
#: sordu ve "veri bulunamadı" cevabı aldı. 0,25 dördünü de geçiriyor.
OWN_DOCUMENT_MIN_SIMILARITY = 0.25


async def _fold_in_own_documents(
    state: MoneyFastState, args: dict[str, Any], result: dict[str, Any]
) -> dict[str, Any]:
    """Kullanıcının kendi belgelerine ayrı bir arama ve ayrı yer.

    Haberle aynı sıralamada yarıştırmak yerine ikinci bir arama yapılıyor:
    biri "piyasada ne söyleniyor", diğeri "bu kullanıcı ne yükledi". İki ayrı
    soru ve tek bir benzerlik sıralaması ikincisini her zaman kaybettiriyor.

    Haber sonuçları KIRPILMIYOR, belgeler önlerine ekleniyor: kullanıcının
    kendi dosyası, sorduğu soruya cevap veren kaynakların en olası olanı.

    Bu arama başarısız olursa tur düşmez -- elde olan haber sonuçlarıyla
    devam eder.
    """
    if not args.get("user_id"):
        return result

    # Haber araması hata verdiyse karışılmıyor: "kaynaklara ulaşılamadı"
    # gerçek bir kesintiyi bildiriyor ve onu kullanıcının kendi belgesiyle
    # örtmek, çalışmayan bir kaynağı çalışıyor gibi göstermek olur.
    if (result.get("specialist_output") or {}).get("status") == "ERROR":
        return result

    own_args = {
        **args,
        "top_k": OWN_DOCUMENT_SLOTS,
        "filters": {"categories": [OWN_DOCUMENT_CATEGORY]},
        "min_similarity": float(
            os.getenv("RAG_OWN_DOCUMENT_MIN_SIMILARITY", str(OWN_DOCUMENT_MIN_SIMILARITY))
        ),
    }
    try:
        own = await get_mcp_client().call("rag_semantic_market_search", own_args)
    except (MCPUnavailable, MCPToolError) as exc:
        log.warning("own-document search failed: %s", exc)
        return result

    documents = (own or {}).get("results") or []
    if not documents:
        return result

    payload = result.get("specialist_output") or {}
    existing = (payload.get("data") or {}).get("results") or []
    seen = {row.get("chunk_id") for row in documents}
    merged = documents + [row for row in existing if row.get("chunk_id") not in seen]

    payload.setdefault("data", {})["results"] = merged
    # Boş bir haber araması, kullanıcının belgesi bulunduğunda artık boş
    # değil: "kaynak bulunamadı" demek yanlış olurdu.
    payload["status"] = "OK"
    return {**result, "specialist_output": payload}


#: Arama sonucunun YAZARA giden alanları. Geri kalanı -- `chunk_id`,
#: `doc_id`, `author`, `language`, `score` -- alma katmanının kendi
#: muhasebesi; yazarın cümlesine giremez, çünkü NAMING kuralı iç adları
#: kullanıcıya yasaklıyor. `sources.build`'in okuduğu dört alan --
#: `title`, `publisher`, `published_at`, `url` -- burada kalıyor: atıf
#: özelliği bu fonksiyonun ÇIKTISI üzerinde çalışıyor.
_WRITER_RESULT_FIELDS = (
    "title",
    "snippet",
    "publisher",
    "published_at",
    "url",
    "tickers",
    "doc_type",
    "is_opinion",
)


def _slim_results(result: dict[str, Any]) -> dict[str, Any]:
    """Kaynakların sentez gövdesine giden hâli: okunacak metin, iç kimlik değil.

    `_slim_posture` ile aynı gerekçe ve aynı ölçülen sebep. Ticker süzgeci
    olan bir arama arşiv etiketlenene kadar hep boş dönüyordu, dolayısıyla bu
    gövdenin sekiz tam belgeyle ne kadar büyüdüğü hiç ölçülmemişti.
    Ölçüldüğünde: "THYAO ile ilgili son haberler neler?" turunda 8.316 token
    istendi, sınır 8.000 -- ve kullanıcı, ASELS'in cevaplandığı bir oturumda
    THYAO için "veri tek seferde işleyebileceğimden büyük çıktı" cevabı aldı.

    Düşen beş alanın hiçbirini yazar okumuyor: ikisi UUID, biri her satırda
    `null`, biri süzgeçle zaten sabit, biri sıralaması bitmiş bir puan.
    Sonuç başına ölçülen ~155 karakter.

    Araç sözleşmesi DEĞİŞMİYOR: `_normalize_result` on üç alanın hepsini
    üretmeye devam ediyor ve doğrudan çağıran onu olduğu gibi alıyor.
    Kırpma yalnızca modele giden kopyada, tekilleştirme (`_fold_in_own_documents`,
    `_narrow_then_widen`) `chunk_id`'yi kullanıp BİTTİKTEN sonra -- bu
    fonksiyon ikisinin de sonunda çalışır.
    """
    payload = result.get("specialist_output") or {}
    data = payload.get("data")
    if not isinstance(data, dict):
        return result
    rows = data.get("results")
    if not isinstance(rows, list) or not rows:
        return result
    slim = [
        {
            key: row[key]
            for key in _WRITER_RESULT_FIELDS
            if isinstance(row, dict) and row.get(key) is not None
        }
        for row in rows
    ]
    return {
        **result,
        "specialist_output": {**payload, "data": {**data, "results": slim}},
    }


#: Kullanıcının Dengeleme ekranını sorduğunu gösteren kelimeler.
#:
#: Araç adı yalnızca plandan okunmuyor, `get_direction_signal`'in `horizon`
#: argümanıyla aynı gerekçe: planlayıcı bu turda risk ölçümüne yönelirse
#: kullanıcı sorduğu ekran hakkında hiçbir şey duymaz. Kelime kümesi DAR --
#: "dengele" tek başına yetmiyor, çünkü "portföyümü nasıl dengelemeliyim"
#: bir SEÇİM sorusu ve cevabı ekranı işaret etmek.
_REBALANCE_SCREEN_WORDS = ("dengeleme ekran", "dengeleme sekme", "dengeleme listesi",
                           "dengeleme planı", "o listede", "bu listede")


def _asks_about_rebalance(state: MoneyFastState) -> bool:
    """Kullanıcı ekranda duran listeyi mi soruyor."""
    message = _fold(state.get("user_message") or "")
    return any(_fold(word) in message for word in _REBALANCE_SCREEN_WORDS)


async def risk_node(state: MoneyFastState) -> dict[str, Any]:
    """Three calls: positions, the profile summary, then the raw statistics.

    The risk tool has no position access by design, hence the first call. The
    second exists because `calculate_portfolio_risk_metrics` returns no score
    and no band -- those are produced by the backend's profile layer, which
    the agent could not reach. Asked "how risky is my portfolio", the risk
    page answered "83 puan, Düşük" and the assistant answered with an
    annualised volatility percentage: one system, one question, two answers,
    and no way for the user to tell which one was the answer.
    """
    mcp = get_mcp_client()
    user_id = state.get("user_id") or "unknown"

    # Dengeleme ekranı SALT OKUMA bir soru ve risk ölçümüne hiç ihtiyacı yok:
    # üç çağrılık zinciri boşuna kurmak, cevabı geciktirmekten başka bir şey
    # yapmazdı. Ekranı sormayan bir turda bu dal hiç girilmiyor.
    if _asks_about_rebalance(state):
        return await _run_tool(
            state, "get_rebalance_plan", {"user_id": user_id},
            assumptions=[],
            # Hedefi olmayan bir kullanıcıda liste YOK ve bu TAM bir cevap:
            # "hedefi siz koyarsınız" demek, boş bir liste göstermekten iyi.
            empty_when=lambda p: not p.get("hasTarget"),
        )

    try:
        holdings = await mcp.call(
            "get_portfolio_positions",
            {"user_id": user_id, "base_currency": "TRY"},
        )
    except (MCPUnavailable, MCPToolError) as exc:
        return _tool_error(state, "get_portfolio_positions", exc)

    positions = holdings.get("positions") or []
    if not positions:
        return {
            "specialist_output": {
                "agent": "RISK_STRATEGY_AGENT",
                "status": "EMPTY",
                "reason": "No positions to measure.",
                "data": None,
            },
            "tools_used": (state.get("tools_used") or []) + ["get_portfolio_positions"],
        }

    # Ölçülemeyen faktör turu, PLAN SORULMADAN kesiliyor.
    #
    # Reddi `_scenario_branch`'e bırakmak yetmiyordu: o yalnızca model
    # `run_portfolio_scenario` seçtiğinde çalışıyor. ÖLÇÜLDÜ -- model bunun
    # yerine `get_portfolio_stress_test`'i seçti, araç düzgün çalıştı ve model
    # döviz ile altın replaylerini FAİZ İÇİN VEKİL olarak kullanıp "faiz
    # artışıyla ilişkili olası TL güçlenmesi..." diye bir okuma kurdu. Araç
    # sözleşmesi bunu açıkça yasaklıyor ve yasak tutmadı.
    #
    # Koşul, yönlendirmeyi zorlayan koşulun AYNISI: tek bir doğru, iki yerde
    # uygulanıyor. Bir LLM çağrısı da tasarruf ediliyor.
    if _is_unmeasurable_factor_turn(state["user_message"]):
        return {
            "specialist_output": {
                "agent": "RISK_STRATEGY_AGENT",
                "status": "UNSUPPORTED",
                "user_message_tr": UNSUPPORTED_FACTOR_TR,
                "data": None,
            },
            "tools_used": (state.get("tools_used") or []) + ["get_portfolio_positions"],
        }

    plan = await _llm_json(
        SPECIALIST_PROMPTS["RISK_STRATEGY_AGENT"], _specialist_task(state), fast=True
    )
    args = plan.get("arguments") or {}
    lookback = args.get("lookback") or "1Y"

    # "Ne olurdu" ailesi: üçü de bu düğümden çıkıyor ve üçü de ÖLÇÜM. Ayrı
    # bir uzman ajan açılmadı, çünkü hepsi aynı portföyü aynı seriden okuyor
    # ve yönlendirmeyi ikiye bölmek, "dolar çıksa ne olur" ile "riskim ne"
    # arasında bir sınır çizmeyi gerektirirdi -- ikisi de risk ölçümü.
    branch = _WHAT_IF_TOOLS.get(plan.get("tool") or "")
    if branch is not None:
        return await branch(state, user_id, args, lookback, plan)

    args["positions"] = positions
    args["lookback"] = lookback
    args.setdefault("confidence_level", 0.95)
    args.setdefault("rebalance_assumption", "BUY_AND_HOLD")

    # Best-effort, and deliberately so. A missing summary costs the turn its
    # score and its declared-tolerance comparison; the statistics below still
    # answer the question. Failing the whole turn over it would trade a
    # partial answer for none.
    summary = None
    try:
        summary = await mcp.call(
            "get_risk_profile_summary",
            {"user_id": user_id, "lookback": args["lookback"]},
        )
    except (MCPUnavailable, MCPToolError) as exc:
        log.warning("risk profile summary unavailable: %s", exc)

    # Aynı sebeple best-effort: teknik görünüm turu zenginleştirir, ayakta
    # tutmaz. Buraya bağlı, MARKET_DATA_AGENT'a değil -- o ajanın holdings
    # erişimi yok ve olmaması bilinçli; portföyün TAMAMINI ölçen tek düğüm bu.
    posture = None
    try:
        posture = await mcp.call("get_portfolio_technicals", {"user_id": user_id})
    except (MCPUnavailable, MCPToolError) as exc:
        log.warning("portfolio technicals unavailable: %s", exc)

    out = await _run_tool(
        state, "calculate_portfolio_risk_metrics", args,
        assumptions=plan.get("assumptions") or [],
        # One correction attempt, as the market-data node has. Measured on the
        # live path: the planner emitted lookback "1y" on one turn and "365"
        # on the next, and a rejected argument became "Verilere ulaşamadım"
        # for a portfolio whose data was entirely present.
        repair_prompt=SPECIALIST_PROMPTS["RISK_STRATEGY_AGENT"],
    )
    tools = ["get_portfolio_positions"] + (out.get("tools_used") or [])
    data = (out.get("specialist_output") or {}).get("data")
    if posture and isinstance(data, dict):
        # Ölçümün yanına, içine değil bir kardeş anahtar olarak da değil:
        # synthesis `data`'yı okuyor. Volatilite ve düşüş, portföyün kendi
        # geçmişine göre nerede DURDUĞUNU söylemiyor -- "riskim ne" sorusunun
        # cevabı iki ölçümün ikisini birden istiyor.
        data["technical_posture"] = _slim_posture(posture)
        tools.append("get_portfolio_technicals")
    if summary and isinstance(data, dict):
        # Carried inside the metrics payload rather than beside it: the
        # synthesis step reads `data`, and a sibling key would need every
        # consumer to learn about it.
        data["profile_summary"] = _slim_summary(summary)
        tools.append("get_risk_profile_summary")
    out["tools_used"] = tools
    return out



# ── "Ne olurdu" dalları ──────────────────────────────────────────────────────
#
# Üçü de RISK_STRATEGY_AGENT'ın arkasında, MARKET_DATA_AGENT'ta değil: hepsi
# kullanıcının PORTFÖYÜNÜ ölçüyor ve o ajanın holdings erişimi yok.


async def _scenario_branch(state, user_id, args, lookback, plan):
    """`run_portfolio_scenario`: bir faktör oynasaydı."""
    factor = str(args.get("factor") or "").upper()
    if factor not in SCENARIO_FACTORS:
        # Ölçülemeyen faktörü aracın 422'sine göndermek yerine burada
        # kesiliyor: en sık geleni FAİZ ve sistemde faiz serisi yok. Bir
        # döviz faktörünü vekil olarak koymak, ölçülmemiş bir sayıyı ölçüm
        # diye vermek olurdu.
        # EMPTY DEĞİL. "Boş" bir sonuç, aracın çalışıp bir şey bulamaması
        # demek ve sentez kuralı onu "veri şu anda yok"a çeviriyor -- ölçüldü,
        # kullanıcıya iki kez "tekrar denememi ister misiniz" dendi. Bu ise
        # kalıcı bir sınır ve cümlesi kodda duruyor.
        return {
            "specialist_output": {
                "agent": "RISK_STRATEGY_AGENT",
                "status": "UNSUPPORTED",
                "user_message_tr": UNSUPPORTED_FACTOR_TR,
                "data": None,
            },
            "tools_used": state.get("tools_used") or [],
        }
    return await _run_tool(
        state, "run_portfolio_scenario",
        {
            "user_id": user_id,
            "factor": factor,
            # Kullanıcı bir büyüklük söylemediyse %10. Varsayım aracın
            # sözleşmesinde de yazılı ve ajana bunu SÖYLEMESİ talimat verilmiş.
            "shock_pct": float(args.get("shock_pct") or 10),
            "lookback": lookback,
        },
        assumptions=plan.get("assumptions") or [],
        empty_when=lambda p: not p.get("statement"),
    )


async def _stress_branch(state, user_id, args, lookback, plan):
    """`get_portfolio_stress_test`: gerçekten olanlar."""
    return await _run_tool(
        state, "get_portfolio_stress_test",
        {"user_id": user_id, "lookback": lookback},
        assumptions=plan.get("assumptions") or [],
        empty_when=lambda p: not p.get("worst_days") and not p.get("replays"),
    )


async def _simulate_branch(state, user_id, args, lookback, plan):
    """`simulate_position_change`: bir alım/satım yapılsaydı.

    Değişikliği SUNUCU ÖNERMEZ. Model bir değişiklik üretmediyse tur burada
    biter ve kullanıcıya sorulur -- kendi kendine bir miktar uydurmak, bir
    öneri motoruna dönüşmenin ilk adımı olurdu.
    """
    changes = [
        {"symbol": str(row["symbol"]).upper(),
         "quantity_delta": float(row["quantity_delta"])}
        for row in (args.get("changes") or [])
        if isinstance(row, dict) and row.get("symbol") and row.get("quantity_delta")
    ]
    if not changes:
        return {
            "specialist_output": {
                "agent": "RISK_STRATEGY_AGENT",
                "status": "NEEDS_INPUT",
                "missing_fields": ["changes"],
                "clarification_request": (
                    "Hangi hisseden ne kadar alıp sattığınızı varsayalım?"
                ),
            },
            "tools_used": state.get("tools_used") or [],
        }
    return await _run_tool(
        state, "simulate_position_change",
        {"user_id": user_id, "changes": changes[:10], "lookback": lookback},
        assumptions=plan.get("assumptions") or [],
        empty_when=lambda p: not p.get("current"),
    )


#: Backend'in `scenario.FACTORS`'ıyla ve aracın `FACTORS`'ıyla AYNI liste.
#: Üçü ayrışırsa model geçersiz bir faktör üretir ve kullanıcı "ölçemedim"
#: cevabı alır -- `ALLOWED_SORTS` ile bir kez yaşanmış bir hata.
SCENARIO_FACTORS = ("USDTRY", "EURTRY", "XU100", "XAUUSD")

#: Kullanıcıya gösterilecek adlar. Sembol sızmaz (`prompts.py`'deki NAMING
#: kuralı); backend'in `scenario.FACTORS`'ındaki adların aynısı.
SCENARIO_FACTOR_NAMES = "Dolar/TL, Euro/TL, BIST 100 ve ons altın"

#: Ölçülemeyen bir faktör istendiğinde kullanıcıya gidecek cümle, KODDA.
#: Modelden istenmiyor, çünkü ölçüldü: aynı durum iki kez "veriler şu anda
#: alınamadı, tekrar denememi ister misiniz" diye anlatıldı -- bir KESİNTİ
#: dili. Oysa faiz serisi yapısal olarak yok; tekrar denemek hiçbir zaman
#: işe yaramayacak ve öyle demek kullanıcıya olmayan bir umut vermek.
UNSUPPORTED_FACTOR_TR = (
    "Faiz ve enflasyon için bu sistemde günlük bir seri tutulmuyor, "
    "dolayısıyla portföyünüzün onlara duyarlılığı ölçülemiyor — bu geçici "
    "bir sorun değil, ölçebildiklerimin sınırı. Ölçebildiğim faktörler: "
    f"{SCENARIO_FACTOR_NAMES}."
)

_WHAT_IF_TOOLS = {
    "run_portfolio_scenario": _scenario_branch,
    "get_portfolio_stress_test": _stress_branch,
    "simulate_position_change": _simulate_branch,
}


def _slim_posture(posture: dict[str, Any]) -> dict[str, Any]:
    """Teknik görünümün YAZARA giden hâli: cümleler, ham gösterge blokları değil.

    Pozisyon başına yirmi alanlık `signals` bloğu EKRANIN ihtiyacı -- tablo
    onu çiziyor. Yazarın ihtiyacı `summary.statement` ve satır başına
    `narrative`; araç sözleşmesi zaten "cümleleri olduğu gibi aktar" diyor ve
    göstergeleri alan adlarıyla anmayı YASAKLIYOR. Alan adlarını yazara
    göndermek hem israf hem de o yasağın önüne yem koymak.

    Ölçüldü ve bu bir GERİLEME düzeltmesi: `technical_posture` eklendiğinde
    risk turunun sentez gövdesi 3.269 karakter büyüdü ve toplam, sağlayıcının
    tek istek sınırını aştı (8.393 token istendi, sınır 8.000). Sonuç,
    kullanıcının bildirdiği davranıştı: aynı soru her seferinde "yoğunluk
    sınırına takıldım" cevabı veriyor, aynı oturumdaki başka sorular anında
    cevaplanıyordu. Kırpma bu bloğu 3.269'dan ~1.440'a indiriyor.

    Sayılar kaybolmuyor, YOLU değişiyor: ekran aynı uç noktadan tam hâlini
    okumaya devam ediyor.
    """
    positions = posture.get("positions") or []
    return {
        "summary": posture.get("summary") or {},
        "positions": [
            {
                "symbol": row.get("symbol"),
                "trend": row.get("trend"),
                "narrative": row.get("narrative"),
            }
            for row in positions
        ],
        "unconvertible": posture.get("unconvertible") or [],
    }

def _slim_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Risk özetinin YAZARA giden hâli.

    `_slim_posture` ile aynı gerekçe ve aynı ölçülen sebep. v2.17 ile özete
    iki karşılaştırma daha eklendi -- ürün grubu beyanı ve kullanıcının kendi
    hedefinden sapma -- ve toplam yine sağlayıcının tek istek sınırını aştı:
    kullanıcı "hedef dağılımımdan ne kadar saptım" sorusuna "tek seferde
    işleyebileceğimden büyük çıktı" cevabı aldı.

    İki blokta da YAZARIN ihtiyacı hazır CÜMLELER, satırlar değil. Satırlar
    EKRANIN ihtiyacı: tablo onlardan çiziliyor ve ekran aynı uç noktadan tam
    hâlini okumaya devam ediyor.

    Satırları da göndermek denendi ve yetmedi. Risk turu bu eklemeden ÖNCE de
    tavana yakındı -- ölçüldü: teknik görünüm 7.463, risk özeti 3.557,
    metrikler 1.605 karakter -- ve sekiz pozisyonlu bir portföyde gövde
    9.744'e çıkıp kırpıldı, istek yine 8.128 token ile 8.000'lik sınırı aştı.
    `allocation_drift.statement` en büyük farkı zaten iki sayısıyla birlikte
    adlandırıyor, dolayısıyla cevabın kendisi cümlede duruyor.
    """
    # `metrics` ve `data_quality` bu gövdede İKİ KEZ bulunuyordu: ölçüm
    # aracının kendi çıktısı zaten aynı turda, aynı `data` sözlüğünde
    # duruyor ve istatistiklerin yetkili kaynağı o. Özetin kopyası yalnızca
    # puanın hangi alt kümeden üretildiğini gösteriyor -- ekranın işi, yazarın
    # değil.
    slim = {
        key: value
        for key, value in summary.items()
        if key not in ("metrics", "data_quality")
    }
    exposure = summary.get("group_exposure")
    if isinstance(exposure, dict):
        slim["group_exposure"] = {
            "assessed": exposure.get("assessed"),
            "statements": [
                row.get("statement") for row in exposure.get("groups") or []
            ],
        }
    drift = summary.get("allocation_drift")
    if isinstance(drift, dict):
        slim["allocation_drift"] = {
            "has_target": drift.get("has_target"),
            "statement": drift.get("statement"),
        }
    return slim


async def _verify_named_instrument(
    state: MoneyFastState, plan: dict[str, Any]
) -> Optional[dict[str, Any]]:
    """Look the named instrument up BEFORE anything is asked about it.

    Measured, from three consecutive turns: "nvvvvdi hissesi almak", "aple
    alcam" and "ndivia nasıl" all reached an answer with `get_market_data`
    NEVER CALLED. The model recognised "aple" as Apple from its own knowledge,
    invented that NVVVVDI does not exist, and told the user data for "ndivia"
    could not be retrieved -- while the backend resolves ndivia to NVDA
    perfectly well.

    The prompt already tells the specialist to check first. A prompt is
    advisory: this module already learned that with `_keep_crisis`, where a
    mandatory instruction was followed about half the time. So the check runs
    in code, on the one path where being wrong costs money.

    Returns a NEEDS_INPUT specialist output when the name does not resolve,
    or None to let the turn continue.
    """
    named = _named_symbol(plan, state)
    if not named:
        return None

    try:
        payload = await get_mcp_client().call("get_market_data", {"symbols": [named]})
    except (MCPUnavailable, MCPToolError):
        # A lookup failure is not proof the instrument is missing. Let the turn
        # continue; staging resolves strictly and refuses on its own.
        return None

    if payload.get("instruments"):
        return None

    # Not found. The tool's warning already carries the candidates the resolver
    # produced, phrased for a person -- pass that through rather than writing a
    # second, differently worded version of the same sentence.
    suggestion = next(
        (w for w in (payload.get("warnings") or []) if "biri mi" in w), None
    )
    return {
        "specialist_output": {
            "agent": "TRANSACTION_AGENT",
            "status": "NEEDS_INPUT",
            "missing_fields": ["instrument"],
            "clarification_request": suggestion or (
                f"«{named}» diye bir enstrüman bulamadım. "
                f"Sembolü ya da tam adını yazar mısınız?"
            ),
        }
    }


def _named_symbol(plan: dict[str, Any], state: MoneyFastState) -> Optional[str]:
    """Whatever instrument this turn is about, however the model expressed it."""
    args = plan.get("arguments") or {}
    instrument = args.get("instrument") or {}
    candidates = [
        instrument.get("symbol") if isinstance(instrument, dict) else None,
        args.get("symbol"),
    ]
    tickers = (state.get("entities") or {}).get("tickers") or []
    candidates.extend(tickers[:1])
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


async def _cancel_order_node(state: MoneyFastState, plan: dict[str, Any]) -> dict[str, Any]:
    """"Emrimi iptal et" — önce OKU, sonra iptal et.

    Model emir numarasını bilemez ve uydurmasına izin verilmiyor
    (`cancel_order`ın sözleşmesi de bunu yasaklıyor), dolayısıyla iptal her
    zaman iki adım: açık emirleri oku, hangisinin kastedildiğini belirle,
    sonra iptal et.

    Belirsizlik SORULUYOR, tahmin edilmiyor. İki bekleyen emri olan birinin
    "emrimi iptal et" demesi, ikisinden birini seçmek için yeterli değil ve
    yanlış olanı iptal etmek geri alınamaz bir şey değil ama kullanıcının
    istemediği bir şey.
    """
    user_id = state.get("user_id") or "unknown"
    listing = await _run_tool(state, "get_open_orders", {"user_id": user_id})
    output = listing.get("specialist_output") or {}
    if output.get("status") == "ERROR":
        return listing

    orders = [
        row for row in ((output.get("data") or {}).get("orders") or [])
        if row.get("cancellable")
    ]

    if not orders:
        return {
            "specialist_output": {
                "agent": "TRANSACTION_AGENT",
                "status": "EMPTY",
                "tool": "get_open_orders",
                "data": output.get("data") or {},
                "assumptions": [],
            },
            "tools_used": listing.get("tools_used") or [],
        }

    # Kullanıcı bir sembol söylediyse aday kümesi ona daralıyor. Söylemediyse
    # tek emir varsa o, birden fazlaysa soruluyor.
    named = (_named_symbol(plan, state) or "").strip().upper()
    if named:
        matched = [row for row in orders if str(row.get("symbol", "")).upper() == named]
        if matched:
            orders = matched

    if len(orders) > 1:
        return {
            "specialist_output": {
                "agent": "TRANSACTION_AGENT",
                "status": "NEEDS_INPUT",
                "missing_fields": ["order_id"],
                "clarification_request": (
                    "Birden fazla bekleyen emriniz var: "
                    + ", ".join(
                        f"{row.get('symbol')} {row.get('type')} {row.get('quantity'):g}"
                        for row in orders
                    )
                    + ". Hangisini iptal edeyim?"
                ),
            },
            "tools_used": listing.get("tools_used") or [],
        }

    return await _run_tool(
        state, "cancel_order",
        {"user_id": user_id, "order_id": orders[0]["id"]},
        assumptions=plan.get("assumptions") or [],
    )


async def transaction_node(state: MoneyFastState) -> dict[str, Any]:
    plan = await _llm_json(SPECIALIST_PROMPTS["TRANSACTION_AGENT"], _specialist_task(state))

    # İptal, hazırlama yolundan ÖNCE: geri alma bir emir vermek değil ve
    # aşağıdaki yön/adet/sembol denetimlerinin hiçbiri ona uymuyor.
    if plan.get("tool") == "cancel_order":
        return await _cancel_order_node(state, plan)

    if plan.get("status") == "NEEDS_INPUT" or not plan.get("arguments"):
        # About to ask for something more -- usually a quantity. Confirm the
        # instrument EXISTS first. Asking "how many NVVVVDI?" and finding out
        # only at staging that there is no such thing is a question that
        # should never have been put.
        #
        # Only on this path: a complete request goes to staging, which already
        # resolves strictly and refuses with suggestions. The measured failures
        # were all of the "asked for a quantity" kind.
        unknown = await _verify_named_instrument(state, plan)
        if unknown is not None:
            return unknown

        return {
            "specialist_output": {
                "agent": "TRANSACTION_AGENT",
                "status": "NEEDS_INPUT",
                "missing_fields": plan.get("missing_fields") or ["unspecified"],
                "clarification_request": plan.get("clarification_request")
                or "Which instrument, how much, and from which account?",
            }
        }
    args = dict(plan["arguments"])

    # Transfers are staged like trades and confirmed by the user. They settle
    # against the banking ledger, not the investment account — routing them
    # through securities settlement is what produced a "Satım" with a blank
    # ticker, priced with brokerage commission.

    # Direction before amount: staging the wrong side of a trade is worse than
    # staging the wrong size of one.
    inverted = _direction_contradicts_message(state, args)
    if inverted is not None:
        emitted, stated = inverted.split("!=")
        return {
            "specialist_output": {
                "agent": "TRANSACTION_AGENT",
                "status": "NEEDS_INPUT",
                "missing_fields": ["transaction_type"],
                "clarification_request": (
                    "İşlemin yönünden emin olamadım: mesajınızı "
                    f"{'satış' if stated == 'SELL' else 'alış'} olarak okudum ama "
                    "hazırlanan öneri "
                    f"{'alış' if emitted == 'BUY' else 'satış'} yönündeydi. "
                    "Alım mı satım mı yapmak istiyorsunuz?"
                ),
            }
        }

    mismatch = _amount_not_in_current_turn(state, args)
    if mismatch is not None:
        log.warning("staging refused, figure overruled by this turn: %s", mismatch)
        return {
            "specialist_output": {
                "agent": "TRANSACTION_AGENT",
                "status": "NEEDS_INPUT",
                "missing_fields": ["quantity" if "quantity" in mismatch else "notional_amount"],
                # The field name stays out of the user's sentence: `mismatch`
                # reads "quantity=250", and the NAMING rule keeps internal
                # keys off the screen. It is logged instead, where it helps.
                "clarification_request": (
                    "Bu mesajda yazdığınız adet ile daha önce konuştuğumuz adet "
                    "farklı görünüyor. Hangisini kullanayım?"
                ),
            }
        }

    refused = _symbol_refused_in_message(state, args)
    if refused is not None:
        log.warning("staging refused, user rejected this symbol: %s", refused)
        return {
            "specialist_output": {
                "agent": "TRANSACTION_AGENT",
                "status": "NEEDS_INPUT",
                "missing_fields": ["instrument.symbol"],
                "clarification_request": (
                    f"{refused} istemediğinizi söylediniz. Hangi hisseyi almak "
                    "veya satmak istediğinizi yazar mısınız?"
                ),
            }
        }

    args["user_id"] = state.get("user_id") or "unknown"
    args["idempotency_key"] = _idempotency_key(state)
    args["assumptions"] = plan.get("assumptions") or []
    out = await _run_tool(state, "prepare_transaction_proposal", args)
    payload = (out.get("specialist_output") or {}).get("data") or {}
    if payload and payload.get("confirmation_required") is not True:
        # Contract violation upstream. Refuse rather than present it.
        log.error("staging returned confirmation_required != true")
        return _tool_error(
            state, "prepare_transaction_proposal",
            RuntimeError("confirmation_required was not true"),
        )
    return out


#: Verbatim crisis resources. Hardcoded rather than generated: asked to
#: produce them the model once offered "ALO 182", which is the MHRS health
#: APPOINTMENT line, not a crisis line. A hallucinated resource is worse than
#: none, because someone may actually dial it.
CRISIS_RESOURCES_TR = (
    "Acil bir tehlike varsa 112'yi arayın. "
    "Sosyal Destek Hattı 183, 7/24 ücretsizdir ve psikososyal destek sağlar."
)

#: Being threatened by someone else is a police matter, not a budgeting one.
COERCION_RESOURCES_TR = (
    "Can güvenliğiniz tehlikedeyse 112'yi arayın. "
    "Kolluk ihbarı için 155 (Polis) veya 156 (Jandarma) aranabilir."
)

#: What the assistant may say once distress is detected. Split by category:
#: these were ONE instruction written for the financial case, so "ölmek
#: istiyorum" was answered with a lecture about how borrowed money raises
#: risk. Self-harm now gets no financial content at all.
_HANDOFF_INSTRUCTIONS = {
    "SELF_HARM_RISK": (
        "The user may be at risk of self-harm. This is not a financial turn. "
        "Respond briefly and warmly in Turkish: acknowledge what they said, "
        "say they do not have to face it alone, and encourage contacting "
        "someone they trust or a professional. "
        "Do NOT mention markets, portfolios, debt, budgeting, investing or "
        "risk tolerance. Do NOT analyse their finances. "
        "Do NOT offer to connect them to an adviser or specialist -- this "
        "product cannot do that, and the offer was previously made and then "
        "refused when accepted. "
        "Do not state phone numbers yourself; they are appended verbatim. "
        "No emoji, no humour, at most four sentences."
    ),
    "COERCION_RISK": (
        "The user reports being threatened or coerced by another person. "
        "This is a safety matter, not an investment one. Respond briefly in "
        "Turkish, take it seriously, and encourage contacting the "
        "authorities or someone they trust. "
        "Do NOT suggest trades, instruments or ways to raise money quickly -- "
        "urgency plus threat is exactly how people are pushed into ruinous "
        "positions. Do not state phone numbers yourself; they are appended. "
        "No emoji, no humour, at most four sentences."
    ),
    "FINANCIAL_DISTRESS": (
        "Do not screen, list instruments, or give a strategy. State "
        "plainly that borrowed money and recovery pressure make risk "
        "materially worse. Offer budgeting basics. Do NOT offer to connect "
        "them to a human adviser -- this product cannot do that. "
        "No emoji, no humour."
    ),
    # A disclosed condition is not a crisis, a threat, or a budgeting
    # problem. "ben şizofrenim" was answered with the FINANCIAL_DISTRESS
    # text -- a lecture on how borrowed money raises risk -- because this
    # category did not exist and that one was the fallback.
    "MENTAL_HEALTH_DISCLOSURE": (
        "The user has disclosed a mental health condition or difficulty. "
        "This is NOT a crisis and NOT a financial turn. Respond briefly and "
        "warmly in Turkish: acknowledge what they shared without dramatising "
        "it, and make clear they are still welcome here. "
        "Do NOT mention markets, portfolios, debt, budgeting, investing or "
        "risk tolerance. Do NOT diagnose, advise on treatment, or ask about "
        "symptoms. Do NOT offer to connect them to an adviser or specialist "
        "-- this product cannot do that. "
        "You MAY offer to continue with whatever they were asking about. "
        "Do not state phone numbers yourself; they are appended verbatim. "
        "No emoji, no humour, at most three sentences."
    ),
    # The fallback. Distress was detected but not identified, so the reply
    # must be safe under EVERY reading of it -- which means no financial
    # content, because the one thing we know is that we do not know which
    # kind of trouble this is.
    "GENERIC_DISTRESS": (
        "The user is in some form of distress that has not been identified. "
        "Respond briefly and warmly in Turkish: acknowledge it, and ask an "
        "open question about what would help. "
        "Do NOT assume the problem is financial. Do NOT mention markets, "
        "portfolios, debt, budgeting or investing unless the user has "
        "already raised them in this turn. Do NOT offer to connect them to "
        "an adviser -- this product cannot do that. "
        "Do not state phone numbers yourself; they are appended verbatim. "
        "No emoji, no humour, at most three sentences."
    ),
}

#: The vocabulary `handoff_node` selects on.
#:
#: The regex pre-filter emits these names, but the ROUTER MODEL emits its own
#: and `router_node` unions them into the same list without checking. Measured:
#: "i am jumping off a cliff" produced `SELF_HARM` -- one character class away
#: from the canonical name -- and `handoff_node`, which matched exact strings
#: and fell through to FINANCIAL_DISTRESS, answered a suicide statement with
#: budgeting tips and no crisis line.
#:
#: The synonyms are the model's observed and plausible outputs. `primary_intent`
#: is read through the same table: in that turn the intent was already
#: `SELF_HARM` and nothing looked at it.
_FLAG_SYNONYMS = {
    "SELF_HARM": "SELF_HARM_RISK",
    "SELF_HARM_RISK": "SELF_HARM_RISK",
    "SELF_INJURY": "SELF_HARM_RISK",
    "SUICIDE": "SELF_HARM_RISK",
    "SUICIDAL": "SELF_HARM_RISK",
    "SUICIDE_RISK": "SELF_HARM_RISK",
    "SUICIDAL_IDEATION": "SELF_HARM_RISK",
    "COERCION": "COERCION_RISK",
    "COERCION_RISK": "COERCION_RISK",
    "THREAT": "COERCION_RISK",
    "EXTORTION": "COERCION_RISK",
    "BLACKMAIL": "COERCION_RISK",
    "MENTAL_HEALTH": "MENTAL_HEALTH_DISCLOSURE",
    "MENTAL_HEALTH_DISCLOSURE": "MENTAL_HEALTH_DISCLOSURE",
    "PSYCHOLOGICAL_DISTRESS": "MENTAL_HEALTH_DISCLOSURE",
    "FINANCIAL_DISTRESS": "FINANCIAL_DISTRESS",
}

#: Most serious first. A turn carrying several is answered as the worst one.
_CATEGORY_PRECEDENCE = (
    "SELF_HARM_RISK",
    "COERCION_RISK",
    "MENTAL_HEALTH_DISCLOSURE",
    "FINANCIAL_DISTRESS",
)

#: Resources per category. FINANCIAL_DISTRESS carries none deliberately: its
#: answer is budgeting, and a crisis line under a debt question would
#: misread the situation back at the user.
_CATEGORY_NOTICES = {
    "SELF_HARM_RISK": [CRISIS_RESOURCES_TR],
    "COERCION_RISK": [COERCION_RESOURCES_TR],
    "MENTAL_HEALTH_DISCLOSURE": [CRISIS_RESOURCES_TR],
    "FINANCIAL_DISTRESS": [],
    "GENERIC_DISTRESS": [CRISIS_RESOURCES_TR],
}


def handoff_category(flags: list[str], primary_intent: str | None = None) -> str:
    """Which distress response this turn gets.

    Unrecognised signals land on GENERIC_DISTRESS, never on
    FINANCIAL_DISTRESS. The cost of the two mistakes is not symmetric: a
    suicidal user handed a budgeting lecture is a far worse outcome than an
    indebted user handed an unnecessarily gentle one, and the fallback is by
    definition the branch taken when we do not know which we are looking at.
    """
    candidates = {
        _FLAG_SYNONYMS[name]
        for name in list(flags) + ([primary_intent] if primary_intent else [])
        if name in _FLAG_SYNONYMS
    }
    for category in _CATEGORY_PRECEDENCE:
        if category in candidates:
            return category
    return "GENERIC_DISTRESS"


async def handoff_node(state: MoneyFastState) -> dict[str, Any]:
    """Unsafe or distress. No tools, no screens, no instruments."""
    flags = state.get("safety_flags") or []
    category = handoff_category(flags, state.get("primary_intent"))
    notices = _CATEGORY_NOTICES[category]

    return {
        "crisis_notices": notices,
        "specialist_output": {
            "agent": "HUMAN_HANDOFF",
            "status": "HANDOFF",
            "safety_flags": flags,
            "handoff_category": category,
            "instruction": _HANDOFF_INSTRUCTIONS[category],
        },
    }



#: Sentez gövdesinin karakter tavanı, TAHMİN DEĞİL ÖLÇÜM.
#:
#: Sağlayıcının sınırı 8.000 token / DAKİKA -- istek başına değil. Bu ayrım
#: ölçülerek öğrenildi: hata gövdesi "tokens per minute (TPM)" diyor ve tek
#: bir turda birden çok çağrı yapıldığında (yönlendirme + planlama + sentez)
#: bütçe çağrılar ARASINDA paylaşılıyor. Aşağıdaki hesap yine de tek çağrının
#: sığması için gerekli, ama yeterli değil.
#:
#: Sabit maliyet ölçüldü:
#: sistem prompt'u 15.874 + şablon 2.029 = 17.903 karakter (~4.475 token).
#: Sohbet geçmişi ölçülen turlarda ~1.500 token tutuyor. Geriye kalan
#: ~2.000 token ≈ 8.000 karakter.
#:
#: Önceki değer 12.000'di ve nereden geldiği yazılı değildi; `technical_posture`
#: eklenince toplam sınırı aştı ve kullanıcı bunu üründe gördü.
SYNTHESIS_PAYLOAD_CHARS = 8000


def _fit_payload(payload: dict[str, Any]) -> str:
    """Uzman çıktısını sentez bütçesine sığdırır ve kırptığında SÖYLER.

    Kırpma son çare: JSON'u ortasından kesmek modele bozuk bir gövde vermek
    demek ve bu gövdeden okunan bir sayı yanlış olabilir. Bu yüzden asıl iş
    kırpmak değil, gövdeyi baştan küçük tutmak (`_slim_posture`); burası
    yalnızca öngörülmemiş bir büyümenin turu bir sağlayıcı hatasına
    çevirmesini engelliyor.

    Sessizce kırpmıyor: bir uyarı satırı, gövdenin neden eksik göründüğünü
    log'da aranabilir kılıyor.
    """
    # Girinti YOK. Ölçüldü: aynı risk turu sıkıştırılmış hâlde 6.388,
    # `indent=2` ile 8.707 karakter -- bütçenin üçte biri, modelin hiçbir
    # işine yaramayan boşluğa gidiyordu. Sekiz pozisyonlu bir portföyde tur
    # bu yüzden sığmıyordu ve kullanıcı "tek seferde işleyebileceğimden büyük
    # çıktı" cevabı alıyordu; kırpma da devreye giriyor ama kırpılmış JSON
    # zaten bozuk bir gövde demek.
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= SYNTHESIS_PAYLOAD_CHARS:
        return text

    # Bileşik bir gövde ORTASINDAN kesilmiyor: parça DÜŞÜRÜLÜYOR ve düşen
    # istek `unanswered`'a geçiyor. Kırpılmış JSON modele bozuk bir gövde
    # vermek demek ve ondan okunan bir sayı yanlış olabilir; eksik bir parça
    # ise söylenebilir bir şey.
    parts = payload.get("parts")
    if isinstance(parts, list) and len(parts) > 1:
        trimmed = dict(payload)
        unanswered = list(payload.get("unanswered") or [])
        while len(parts) > 1 and len(text) > SYNTHESIS_PAYLOAD_CHARS:
            dropped = parts[-1]
            parts = parts[:-1]
            unanswered.append(dropped.get("request") or "")
            trimmed["parts"] = parts
            trimmed["unanswered"] = [r for r in unanswered if r]
            text = json.dumps(trimmed, ensure_ascii=False, separators=(",", ":"))
        log.warning(
            "compound payload trimmed to %d part(s) to fit the budget", len(parts)
        )
        if len(text) <= SYNTHESIS_PAYLOAD_CHARS:
            return text
    log.warning(
        "synthesis payload truncated: %d -> %d chars", len(text), SYNTHESIS_PAYLOAD_CHARS
    )
    return text[:SYNTHESIS_PAYLOAD_CHARS]


#: Tek bir arama sonucundan alınacak en fazla metin.
#:
#: Sekiz sonuç x 500 karakter, artı sonuç başına ~150 karakterlik künye,
#: `SYNTHESIS_PAYLOAD_CHARS`'ın (8.000) epey altında kalıyor. Sayı ona göre
#: seçildi: `_fit_payload`'ın son çare kırpması gövdeyi ORTASINDAN kesiyor
#: ve `_normalize_result` künyeyi metinden önce yazsa bile, oraya kadar
#: gitmemek daha iyi. Burada kırpmak metne mal oluyor, atfa değil.
MAX_SNIPPET_CHARS = 500


def _trimmed_for_synthesis(payload: dict) -> dict:
    """Uzun pasajları kısalt, ama sonuç DÜŞÜRME.

    Bütçe eskiden serileştirilmiş gövdenin tamamına uygulanıyordu ve kesme
    bir sonucun ortasına düştüğünde o sonucun metni kalıp `url`'i gidiyordu;
    prompt da bu durumda modele "bağlantı yoksa yayıncının adını yaz"
    diyor. Görünen sonuç, sonraki kaynakların tıklanabilir atıflarını
    sessizce kaybetmesiydi. KAP gövdeleri haber özetlerinden uzun olduğu
    için bu, sınırda değil sürekli olacaktı.

    Sonuç başına kırpmak, kesmenin metne mal olmasını sağlıyor -- atfa değil.
    """
    data = payload.get("data")
    if not isinstance(data, dict):
        return payload
    results = data.get("results")
    if not isinstance(results, list):
        return payload

    trimmed = []
    for result in results:
        if isinstance(result, dict) and isinstance(result.get("snippet"), str):
            snippet = result["snippet"]
            if len(snippet) > MAX_SNIPPET_CHARS:
                result = {**result, "snippet": snippet[:MAX_SNIPPET_CHARS] + "…"}
        trimmed.append(result)
    return {**payload, "data": {**data, "results": trimmed}}


#: Kaynak özeti başlığı ve boş hâli. Metin KODDA kuruluyor: bu düğüm hiç
#: model çağırmıyor ve çağırmaması asıl mesele -- turu öldüren şey tam da
#: kota hatasıydı.
RECAP_HEADER_TR = "Bu cevabı şu kaynaklardan kurdum:"
RECAP_EMPTY_TR = (
    "Önceki cevabı belgeye dayandırmamıştım; gösterebileceğim bir kaynak yok. "
    "İsterseniz bir şirket ya da konu adı verin, derlemede arayayım."
)


async def sources_recap_node(state: MoneyFastState) -> dict[str, Any]:
    """Önceki turun kaynaklarını yeniden yüzeye çıkar.

    **Hiç model çağırmıyor.** Ölçüldü: kullanıcı "bana kaynakça verir misin"
    diye sorduğunda cümle arama sorgusu olarak gönderildi, sıfır sonuç döndü,
    ve ardından Groq kota hatası turu öldürdü -- kullanıcı "yoğunluk
    sınırına takıldım" cevabı aldı. Elde olan bir listeyi biçimlendirmek
    için model gerekmiyor, ve gerekmediği için bu tur o hataya bağışık.

    Uygunluk kapısı yine çalışıyor: `draft_response` yazılıyor ve düğüm
    kapıya devrediyor, yani fail-closed davranış korunuyor.
    """
    rows = sources.prior(state)
    if not rows:
        return {"draft_response": RECAP_EMPTY_TR, "specialist_output": {}}

    lines = [RECAP_HEADER_TR, ""]
    for row in rows:
        label = str(row.get("label") or "").strip()
        detail = str(row.get("detail") or "").strip()
        url = row.get("url")
        # Bağlantı varsa markdown; yoksa düz metin. Model yazmıyor,
        # dolayısıyla uydurulmuş bir bağlantı buraya giremez.
        head = f"[{label}]({url})" if url else label
        lines.append(f"- {head}{f' — {detail}' if detail else ''}")
    return {"draft_response": "\n".join(lines), "specialist_output": {}}

async def synthesis_node(state: MoneyFastState) -> dict[str, Any]:
    """Turn the internal envelope into the Turkish user-facing draft."""
    revision = int(state.get("revision_count") or 0)
    try:
        if revision > 0 and state.get("draft_response"):
            task = REVISION_TASK_TEMPLATE.format(
                previous_draft=state["draft_response"],
                blocked_reason=state.get("blocked_reason") or "Compliance rejection.",
            )
        else:
            task = SYNTHESIS_TASK_TEMPLATE.format(
                user_message=state["user_message"],
                # The writer used to be blind to earlier turns, so a
                # follow-up like "peki ya onu satsam?" was rendered by a
                # model that did not know what "onu" referred to. The
                # template's own rules keep this to coreference and tone:
                # figures still come only from the specialist output below.
                conversation_summary=_history_summary(state) or "(none)",
                primary_intent=state.get("primary_intent") or "UNKNOWN",
                target_agent=state.get("target_agent") or "EDUCATION_AGENT",
                specialist_json=_fit_payload(
                    _trimmed_for_synthesis(state.get("specialist_output") or {})
                ),            )
        draft = await _llm_text(ORCHESTRATOR_SYSTEM_PROMPT, task)
    except Exception as exc:  # LLM outage
        log.error("synthesis failed: %s", exc)
        return {
            "draft_response": "",
            "final_output": _failure_message(exc),
            "errors": (state.get("errors") or []) + [f"synthesis: {exc}"],
        }
    return {"draft_response": draft}


#: Koşullu bir okumanın ayrılmaz yarısı. Backend'in `scenario.HEDGE_TR`'si ve
#: `technicals.HEDGE_TR`'si ile AYNI cümle -- üç yerde üç farklı çekince
#: yazmak, birinin daha az bağlayıcı olduğu izlenimi verirdi.
SCENARIO_HEDGE_TR = (
    "Bu bir tahmin değil, geçmiş birlikte hareketin ölçümüdür; geçmiş fiyat "
    "hareketi geleceği belirlemez."
)

#: Çekincenin metinde zaten geçtiğini anlamak için aranan parça. Tam cümleyi
#: aramak, modelin küçük bir yeniden ifadesinde ikinci bir kopya eklerdi.
_HEDGE_MARK = "geleceği belirlemez"

#: Çekincenin garanti edildiği araçlar. Hepsi KOŞULLU okuma üretiyor.
#:
#: `get_direction_signal` v2.21 ile eklendi ve sebebi yine ÖLÇÜLDÜ: "ASELS
#: önümüzdeki 3 ayda nasıl gider" turunda araç `narrative`i çekincesiyle
#: birlikte döndürdü, model onu EXPECTATION MANAGEMENT'ın madde yapısına
#: çevirdi ve kapanış çekincesini düşürdü. Kalan metin dokuz ölçüm ve
#: "Veriler ağırlıklı olarak artış yönündeki baskıya işaret ediyor" idi --
#: koşulsuz ve çekincesiz.
#:
#: `get_technical_signals` de burada, aynı sebeple: o da `technicals.narrate`
#: ile koşullu bir okuma üretiyor ve aynı yeniden yazma ona da yapılabilir.
HEDGED_TOOLS = frozenset(
    {
        "run_portfolio_scenario",
        "get_portfolio_stress_test",
        "simulate_position_change",
        "get_direction_signal",
        "get_technical_signals",
    }
)


#: Dengeleme listesinin kendi çekincesi. Genel uygunluk açıklaması bunun
#: yerini TUTMUYOR: o, içeriğin yatırım danışmanlığı olmadığını söylüyor; bu
#: ise listenin KİMİN hedefinden çıktığını -- kullanıcının kendi girdiği
#: hedeften.
PLAN_DISCLAIMER_TR = (
    "Bu liste yatırım tavsiyesi değildir; kendi belirlediğiniz hedefin "
    "aritmetik karşılığıdır."
)

_PLAN_MARK = "kendi belirlediğiniz hedefin"


def _keep_plan_disclaimer(
    state: MoneyFastState, out: dict[str, Any]
) -> dict[str, Any]:
    """Dengeleme listesinin çekincesini kapının HER dalından geçirir.

    `_keep_hedge` ile aynı ders ve aynı ölçüm: prompt tavsiyedir. Araç
    sözleşmesi "`disclaimer`ı her satırla birlikte aktar" diyor ve ÖLÇÜLDÜ --
    model listeyi tabloya çevirdi, planın kendi çekincesini düşürdü ve yerine
    genel uygunluk cümlesini koydu. Dahası "dengeleme önerileri oluşturdum"
    diye yazdı: listeyi KENDİSİNİN ürettiğini iddia etti.

    Çekince o iddiayı da düzeltiyor, çünkü listenin kullanıcının kendi
    hedefinden çıktığını söylüyor.
    """
    if "get_rebalance_plan" not in set(state.get("tools_used") or []):
        return out
    if _PLAN_MARK in (out.get("final_output") or ""):
        return out
    existing = out.get("disclosures") or []
    if any(_PLAN_MARK in item for item in existing):
        return out
    out["disclosures"] = existing + [PLAN_DISCLAIMER_TR]
    return out


#: Haber yorumunun kendi çekincesi. Genel uygunluk açıklaması bunun yerini
#: TUTMUYOR: o, içeriğin yatırım danışmanlığı olmadığını söylüyor; bu ise
#: içeriğin bir ÖLÇÜM DEĞİL, bir modelin metin okuması olduğunu. Sistemdeki
#: başka hiçbir araç bunu söylemek zorunda değil, çünkü başka hiçbiri bir
#: model yargısı taşımıyor.
NEWS_DIGEST_DISCLAIMER_TR = (
    "Bu özet, haber metinlerinin yapay zeka tarafından yorumlanmasıdır; "
    "yatırım tavsiyesi değildir ve haberin fiyata nasıl yansıyacağını "
    "belirlemez."
)

_DIGEST_MARK = "yapay zeka tarafından yorumlanmasıdır"


def _keep_news_disclaimer(
    state: MoneyFastState, out: dict[str, Any]
) -> dict[str, Any]:
    """Haber yorumunun çekincesini kapının HER dalından geçirir.

    `_keep_plan_disclaimer` ve `_keep_hedge` ile aynı ders: prompt tavsiyedir.
    Araç sözleşmesi "`disclaimer`ı değiştirmeden aktar" diyor, ama bu depoda
    aynı talimatın iki kez ölçülüp iki kez tutulmadığı biliniyor -- senaryo
    çekincesinde ve dengeleme listesinde.

    Burada kaybı daha ağır: kullanıcının okuduğu her cümle bir modelin metin
    okuması ve bunu söyleyen tek şey bu çekince. Düştüğünde geriye, ölçülmüş
    bir bulgudan ayırt edilemeyen bir yorum kalıyor.
    """
    if "get_news_impact_digest" not in set(state.get("tools_used") or []):
        return out
    if _DIGEST_MARK in (out.get("final_output") or ""):
        return out
    existing = out.get("disclosures") or []
    if any(_DIGEST_MARK in item for item in existing):
        return out
    out["disclosures"] = existing + [NEWS_DIGEST_DISCLAIMER_TR]
    return out


def _keep_hedge(state: MoneyFastState, out: dict[str, Any]) -> dict[str, Any]:
    """Koşullu bir turun çekincesini kapının HER dalından geçirir.

    `_keep_crisis` ile aynı sebep ve aynı ders: prompt tavsiyedir. Araç
    sözleşmesi "`statement`'ı çekincesiyle birlikte olduğu gibi aktar" diyor
    ve ÖLÇÜLDÜ -- model senaryo cümlesini yeniden yazdı ve kapanış çekincesini
    düşürdü. Kalan metin "portföyünüzün değeri yaklaşık %6,8 azalır" idi:
    koşulsuz, çekincesiz, ve ölçümün söylemediği bir kesinlikte.

    Genel uygunluk açıklaması (DISC-GENERAL) bunun yerini tutmuyor: o
    içeriğin yatırım danışmanlığı olmadığını söylüyor, bu ise sayının bir
    tahmin değil bir ölçüm olduğunu.

    Metin çekinceyi zaten taşıyorsa ikinci kez eklenmiyor.
    """
    if not (HEDGED_TOOLS & set(state.get("tools_used") or [])):
        return out
    if _HEDGE_MARK in (out.get("final_output") or ""):
        return out
    existing = out.get("disclosures") or []
    if any(_HEDGE_MARK in item for item in existing):
        return out
    out["disclosures"] = existing + [SCENARIO_HEDGE_TR]
    return out


def _keep_crisis(state: MoneyFastState, out: dict[str, Any]) -> dict[str, Any]:
    """Ensure a distress turn carries its resources out of the gate.

    Applied to every branch, BLOCK included. A blocked crisis turn used to end
    at a generic failure string with nothing actionable in it, which is the
    worst moment to hand someone a dead end.

    Koşullu okumanın çekincesi de buradan geçiyor. Ayrı bir sarmalayıcı,
    kapının yedi dalından birinin unutulması demekti -- bu fonksiyon zaten
    hepsinden geçiyor.
    """
    out = _keep_hedge(state, out)
    out = _keep_plan_disclaimer(state, out)
    out = _keep_news_disclaimer(state, out)
    notices = state.get("crisis_notices") or []
    if not notices:
        return out
    existing = out.get("disclosures") or []
    out["disclosures"] = existing + [n for n in notices if n not in existing]
    return out


async def compliance_gate_node(state: MoneyFastState) -> dict[str, Any]:
    """Deterministic gate. Fail closed on any error."""
    draft = state.get("draft_response") or ""
    if not draft:
        return _keep_crisis(state, {
            "compliance_verdict": "BLOCK",
            "final_output": state.get("final_output") or GENERIC_FAILURE_TR,
        })

    specialist = state.get("specialist_output") or {}
    try:
        verdict = await get_mcp_client().call(
            "validate_compliance_rules",
            {
                "draft_response": draft,
                "user_query": state["user_message"],
                "jurisdiction": JURISDICTION,
                "tools_used": state.get("tools_used") or [],
                "contains_personal_data": bool(
                    (specialist.get("data") or {}).get("positions")
                ),
                "contains_transaction_proposal": bool(
                    (specialist.get("data") or {}).get("proposal_id")
                ),
                "strictness": "STANDARD",
            },
        )
    except (MCPUnavailable, MCPToolError) as exc:
        log.error("compliance unavailable, failing closed: %s", exc)
        return _keep_crisis(state, {
            "compliance_verdict": "BLOCK",
            "final_output": GENERIC_FAILURE_TR,
            "errors": (state.get("errors") or []) + [f"compliance: {exc}"],
        })

    decision = (verdict.get("verdict") or "BLOCK").upper()
    log.info(
        "compliance verdict=%s severity=%s audit=%s",
        decision, verdict.get("max_severity"), verdict.get("audit_id"),
    )

    if decision == "PASS":
        return _keep_crisis(state, {
            "compliance_verdict": "PASS",
            "compliance": verdict,
            "final_output": _without_disclosures(draft, verdict),
            "disclosures": _disclosure_texts(verdict),
        })
    if decision == "REVISE":
        remediated = verdict.get("remediated_response") or ""
        if not remediated:
            return _keep_crisis(state, {
                "compliance_verdict": "BLOCK",
                "compliance": verdict,
                "final_output": GENERIC_FAILURE_TR,
            })
        return _keep_crisis(state, {
            "compliance_verdict": "REVISE",
            "compliance": verdict,
            "final_output": _without_disclosures(remediated, verdict),
            "disclosures": _disclosure_texts(verdict),
        })

    # BLOCK
    reason = verdict.get("blocked_reason_user_facing") or GENERIC_FAILURE_TR
    return _keep_crisis(state, {
        "compliance_verdict": "BLOCK",
        "compliance": verdict,
        "blocked_reason": reason,
        "final_output": reason,
        "revision_count": int(state.get("revision_count") or 0) + 1,
    })


# ---------------------------------------------------------------------------
# Conditional edges
# ---------------------------------------------------------------------------
SpecialistRoute = Literal[
    "portfolio", "market_data", "market_research", "risk", "transaction",
    "handoff", "sources_recap", "compound", "synthesis"]


#: Bir turda kaç ayrı istek işlenir.
#:
#: İki, ve sebebi bütçe: sentez gövdesi sağlayıcının 8.000 token'lık istek
#: sınırına dayanmış durumda ve tek bir risk turu ölçüldüğünde 6.400 karakter
#: tutuyor. Üçüncü bir parça, cevabı olan iki parçayı da düşürürdü.
#:
#: Kırpılan istek SESSİZCE düşmüyor: `_compound_payload` neyin dışarıda
#: kaldığını taşıyor ve sentez bunu söylüyor. Sorulmuş ama cevaplanmamış bir
#: soru, hiç sorulmamış gibi davranılacak bir şey değil.
MAX_SUB_REQUESTS = 2

#: Ajan adından graf düğümüne. `route_after_router` ile aynı tablo, ama orası
#: bir dal seçiyor; burası bir fonksiyon çağırıyor.
_NODE_FOR_AGENT = {
    "PORTFOLIO_AGENT": "portfolio",
    "MARKET_DATA_AGENT": "market_data",
    "MARKET_RESEARCH_AGENT": "market_research",
    "RISK_STRATEGY_AGENT": "risk",
    "TRANSACTION_AGENT": "transaction",
}


async def compound_node(state: MoneyFastState) -> dict[str, Any]:
    """Birden çok isteği olan bir turu, istek başına bir uzmana dağıtır.

    Ölçülen kusur: "AKBNK kaç lira ve portföyümün riski ne durumda" TEK bir
    ajana gidiyordu ve cevap "AKBNK fiyatı şu anda alınamıyor. Portföyünüzün
    riski hakkında da veri bulunamadı." oluyordu -- ikisi de fazlasıyla
    mevcutken. Yönlendirici bir ajan seçmek zorunda kalınca, seçtiği ajanın
    aracı diğer yarıyı cevaplayamıyor ve o yarı "veri yok" diye geçiyor.

    Sözleşme bunu BAŞTAN BERİ tarif ediyordu: `classify_and_route_intent`
    `is_compound` ve `sub_requests` döndürüyor ve aracın kendi belgesi
    "is_compound true ise her alt istek için bir kez yeniden çağır" diyor.
    Hiçbir şey okumuyordu.

    Her parça kendi ajanına gidiyor: uzman seçimi parça başına yapılıyor,
    çünkü bileşik bir turun iki yarısı tam olarak farklı ajanlara ait olduğu
    için bileşik.

    Bir parçanın düşmesi diğerini DÜŞÜRMEZ: hatası kendi parçasında
    taşınıyor ve sentez cevaplanabilenleri cevaplıyor. Tek bir aracın
    hatasının turun tamamını "veriye ulaşamadım"a çevirmesi, bu kusurun
    kendisiydi.
    """
    requests = list(state.get("sub_requests") or [])
    dropped = [entry["request"] for entry in requests[MAX_SUB_REQUESTS:]]
    parts: list[dict[str, Any]] = []
    tools: list[str] = list(state.get("tools_used") or [])

    for entry in requests[:MAX_SUB_REQUESTS]:
        request, agent = entry["request"], entry["agent"]
        node = _NODE_FOR_AGENT.get(agent)
        if node is None:
            # Kendi aracı olmayan ajan (EDUCATION, SMALLTALK): parça bir
            # araç turu değil, sentezin doğrudan cevaplayacağı bir soru.
            parts.append({"request": request, "agent": agent, "output": None})
            continue
        branch = {**state, "user_message": request, "target_agent": agent}
        try:
            result = await _SPECIALIST_NODES[node](branch)
        except Exception as exc:  # pragma: no cover - savunma
            log.warning("compound part failed (%s): %s", agent, exc)
            parts.append({"request": request, "agent": agent, "output": None})
            continue
        parts.append({
            "request": request,
            "agent": agent,
            "output": result.get("specialist_output"),
        })
        tools.extend(result.get("tools_used") or [])

    return {
        "specialist_output": {
            "agent": "COMPOUND",
            "status": "OK" if any(p["output"] for p in parts) else "EMPTY",
            "parts": parts,
            # Sorulmuş ama işlenmemiş istekler. Sessizce düşmüyorlar.
            "unanswered": dropped,
        },
        "tools_used": tools,
    }


#: Düğüm adından fonksiyona. Graf `build_graph`'te kuruluyor ama bileşik
#: düğümü uzmanları DOĞRUDAN çağırıyor: graf içinden graf çalıştırmak, aynı
#: turu iki kez izlemek ve iki kez uyumluluk kapısından geçirmek olurdu.
_SPECIALIST_NODES: dict[str, Any] = {}


def _parse_sub_requests(raw: Any) -> list[dict[str, str]]:
    """Alt istekler, her biri kendi ajanıyla.

    Ajan AYNI ÇAĞRIDA geliyor, parça başına ikinci bir yönlendirme çağrısıyla
    değil. Önce öyle yazıldı ve ölçüldüğünde sağlayıcının dakikalık token
    sınırına takıldı: bileşik bir tur router + parça başına yönlendirme +
    parça başına planlama + sentez ile altı LLM çağrısı yapıyordu ve ikinci
    parçanın yönlendirmesi 429 alıyordu. Yönlendirici turu zaten
    sınıflandırıyor; ikinci kez sormak, bildiğini yeniden sormaktı.

    Tanınmayan ajan adı EDUCATION'a düşüyor: uydurulmuş bir ad gerçek bir
    uzmana ulaşmamalı.
    """
    parsed: list[dict[str, str]] = []
    for entry in raw or []:
        if isinstance(entry, dict):
            request = str(entry.get("request") or "").strip()
            agent = str(entry.get("agent") or "")
        else:
            # Eski biçim: düz metin listesi. Ajanı yok, sentez cevaplar.
            request, agent = str(entry).strip(), ""
        if not request:
            continue
        parsed.append({
            "request": request,
            "agent": agent if agent in AGENTS else "EDUCATION_AGENT",
        })
    return parsed


def route_after_router(state: MoneyFastState) -> SpecialistRoute:
    """Pick the specialist. Safety decides first; uncertainty does not decide.

    `needs_clarification` used to short-circuit straight to synthesis, which
    meant the tool was never called and the user was told the data could not
    be retrieved -- when nothing had tried to retrieve it. Measured over one
    session: "onun son fiyatı ne kadar" routed correctly to MARKET_DATA_AGENT,
    was flagged uncertain, skipped the tool, and answered "fiyat alınamadı"
    while the quote sat one call away.

    The flag is not ignored, it is demoted. The specialist runs, and it is the
    specialist that reports NEEDS_INPUT when a field really is missing -- an
    answer grounded in what the tools could actually resolve, rather than a
    guess made before asking. Every specialist here is read-only except
    TRANSACTION, and that one only ever STAGES: nothing reaches the user's
    money without the on-screen confirmation step.
    """
    intent = state.get("primary_intent")
    if intent == "UNSAFE" or "DISTRESS_SIGNAL" in (state.get("safety_flags") or []):
        return "handoff"
    # Önceki turun kaynağını soran bir tur arama YAPMAZ. Ayrı bir düğüm,
    # çünkü tek işi elde olanı biçimlendirmek ve bunu hiç model çağırmadan
    # yapıyor -- turu öldüren kota hatasına bağışık olmasının sebebi bu.
    #
    # Bileşik kontrolden ÖNCE: "bana kaynakça verir misin" iki soru değil,
    # sıfır soru -- aranacak bir şey yok, gösterilecek bir şey var.
    if state.get("meta_request") == "SOURCES_RECAP":
        return "sources_recap"
    # Güvenlikten SONRA: bileşik bir tur da olsa, sıkıntı sinyali taşıyan bir
    # mesaj önce insana gider.
    if state.get("sub_requests"):
        return "compound"
    return {
        "PORTFOLIO_AGENT": "portfolio",
        "MARKET_DATA_AGENT": "market_data",
        "MARKET_RESEARCH_AGENT": "market_research",
        "RISK_STRATEGY_AGENT": "risk",
        "TRANSACTION_AGENT": "transaction",
        "HUMAN_HANDOFF": "handoff",
    }.get(state.get("target_agent") or "", "synthesis")


def route_after_compliance(state: MoneyFastState) -> Literal["synthesis", "__end__"]:
    if state.get("compliance_verdict") == "BLOCK":
        used = int(state.get("revision_count") or 0)
        if used <= MAX_COMPLIANCE_REVISIONS and state.get("draft_response"):
            log.info("compliance blocked, revision attempt %d", used)
            return "synthesis"
    return END


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------
def _traced(name: str, fn):
    """Record one node's input, output and duration.

    Wrapped here rather than inside each node: registration is the one place
    that already names every stage, so both `run_turn` and
    `run_turn_streaming` are covered without either knowing tracing exists.
    """
    async def wrapper(state: MoneyFastState) -> dict[str, Any]:
        with agent_trace.span("node", name, input=dict(state)) as sp:
            out = await fn(state)
            sp.set(output=out)
            return out

    wrapper.__name__ = getattr(fn, "__name__", name)
    return wrapper


def _resilient(name: str, fn):
    """Bir uzman düğümünün çökmesi turu düşürmesin.

    Uzman düğümlerinin HİÇBİRİNDE try/except yoktu. Bir kota hatası
    orada grafın dışına çıkıyor, `api.py` 500 veriyor, backend 502'ye
    çeviriyor ve `record_turn` hiç çalışmıyor -- yani kullanıcının kendi
    mesajı bile kaydedilmiyordu. Sentez düğümünde bu ele alınmıştı,
    uzmanlarda alınmamıştı.

    Yakalanan hata `specialist_output`'a ERROR olarak yazılıyor: sentez
    o durumda elindekiyle -- ve varsa toplanmış kaynaklarla -- devam
    ediyor, boş bir ekran yerine.

    Uygunluk kapısı BİLEREK sarılmıyor: orada açık başarısızlık, modelin
    ürettiğini denetleyen kontrolü sessizce devre dışı bırakmak olurdu.
    """

    async def wrapper(state: MoneyFastState) -> dict[str, Any]:
        try:
            return await fn(state)
        except Exception as exc:  # noqa: BLE001
            log.error("%s node failed: %s", name, exc)
            return {
                "specialist_output": {
                    "agent": state.get("target_agent") or name.upper(),
                    "status": "ERROR",
                    "tool": None,
                    "data": {},
                    "error": _failure_message(exc),
                },
                "errors": (state.get("errors") or []) + [f"{name}: {exc}"],
            }

    wrapper.__name__ = getattr(fn, "__name__", name)
    return wrapper


def _register_specialists() -> None:
    """Bileşik düğümünün çağırdığı uzmanlar.

    Modül düzeyinde değil bir fonksiyonda: düğümler bu satırların ALTINDA
    tanımlı ve modül düzeyinde bir sözlük onları göremezdi.
    """
    _SPECIALIST_NODES.update({
        "portfolio": portfolio_node,
        "market_data": market_data_node,
        "market_research": market_research_node,
        "risk": risk_node,
        "transaction": transaction_node,
    })

def build_graph():
    _register_specialists()
    g = StateGraph(MoneyFastState)
    g.add_node("router", _traced("router", router_node))
    g.add_node("portfolio", _traced("portfolio", _resilient("portfolio", portfolio_node)))
    g.add_node("market_data", _traced("market_data", _resilient("market_data", market_data_node)))
    g.add_node("market_research", _traced("market_research", _resilient("market_research", market_research_node)))
    g.add_node("risk", _traced("risk", _resilient("risk", risk_node)))
    g.add_node("transaction", _traced("transaction", _resilient("transaction", transaction_node)))
    g.add_node("handoff", _traced("handoff", handoff_node))
    g.add_node("sources_recap", _traced("sources_recap", sources_recap_node))
    g.add_node("compound", _traced("compound", compound_node))
    g.add_node("synthesis", _traced("synthesis", synthesis_node))
    g.add_node("compliance", _traced("compliance", compliance_gate_node))

    g.add_edge(START, "router")
    g.add_conditional_edges(
        "router",
        route_after_router,
        {
            "portfolio": "portfolio",
            "market_data": "market_data",
            "market_research": "market_research",
            "risk": "risk",
            "transaction": "transaction",
            "handoff": "handoff",
            "sources_recap": "sources_recap",
            "compound": "compound",
            "synthesis": "synthesis",
        },
    )
    # Sentezi ATLAYIP doğrudan kapıya gidiyor: özetlenecek metin zaten
    # hazır ve modelden geçirmek, bu düğümün var olma sebebini -- hiç model
    # çağırmamasını -- ortadan kaldırırdı.
    g.add_edge("sources_recap", "compliance")
    for node in ("portfolio", "market_data", "market_research", "risk",
                 "transaction", "handoff", "compound"):        g.add_edge(node, "synthesis")
    g.add_edge("synthesis", "compliance")
    g.add_conditional_edges(
        "compliance", route_after_compliance, {"synthesis": "synthesis", END: END}
    )

    checkpointer = None
    try:
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()
    except ImportError:  # optional
        log.info("no checkpointer available, running stateless")
    return g.compile(checkpointer=checkpointer) if checkpointer else g.compile()


@lru_cache(maxsize=1)
def get_graph():
    return build_graph()


def _initial_state(
    user_message: str,
    user_id: str,
    conversation_history: Optional[list[dict[str, str]]],
) -> MoneyFastState:
    """The turn's starting state. Shared by the buffered and streaming runs so
    the two can never drift on what gets reset."""
    state: MoneyFastState = {
        "user_message": user_message,
        "conversation_history": conversation_history or [],
        "user_id": user_id,
        "locale": DEFAULT_LOCALE,
        # Everything below is reset explicitly because the checkpointer keys
        # state on thread_id and MERGES this input into whatever the previous
        # turn left behind. Without the reset, a turn that runs no tool
        # inherits the last one's specialist_output -- and synthesis reads
        # that as its source of figures, so an unrelated later answer can
        # quote an earlier question's holdings. The observed symptom was
        # milder and just as wrong: a refusal rendered with the previous
        # turn's transaction confirm button attached.
        "primary_intent": "",
        "target_agent": "",
        "specialist_output": {},
        "draft_response": "",
        "final_output": "",
        "compliance_verdict": "",
        "compliance": {},
        # Both were missing from this reset. The BLOCK branch does not set
        # `disclosures`, so a blocked turn rendered the PREVIOUS turn's
        # notices; and crisis resources would otherwise follow a distress
        # turn into the next unrelated question about a share price.
        "disclosures": [],
        "crisis_notices": [],
        "blocked_reason": None,
        "entities": {},
        # Aynı gerekçe: checkpointer thread_id üzerinden birleştiriyor, o
        # yüzden bu turda yazılmayan bir alan öncekinin değerini taşır.
        # Taşınan hisse ADI kasten her turda yeniden hesaplanıyor -- konuşma
        # THYAO'dan ASELS'e döndüğünde eskisinin yapışıp kalmaması için.
        "carried_ticker": None,
        "meta_request": None,
        "safety_flags": [],
        "needs_clarification": False,
        "clarifying_question": None,
        "tools_used": [],
        "revision_count": 0,
        "errors": [],
    }
    return state


def _graph_config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": 25}


async def run_turn(
    user_message: str,
    user_id: str = "anonymous",
    conversation_history: Optional[list[dict[str, str]]] = None,
    thread_id: str = "default",
) -> dict[str, Any]:
    agent_trace.new_turn(thread_id)
    state = _initial_state(user_message, user_id, conversation_history)
    return await get_graph().ainvoke(state, config=_graph_config(thread_id))


#: What each graph node is doing, in the user's language.
#:
#: These replace a hardcoded 800ms ticker on the client that cycled four
#: captions regardless of what ran -- it announced "Risk modeli
#: güncelleniyor..." for "what is the capital of Turkey". Naming a stage the
#: system did not enter is the same class of error as showing a price the
#: system did not fetch.
STAGE_LABELS_TR = {
    "router": "Talebiniz sınıflandırılıyor...",
    "portfolio": "Portföyünüz okunuyor...",
    "market_data": "Piyasa verileri çekiliyor...",
    "market_research": "Kaynaklar taranıyor...",
    "risk": "Risk ölçütleri hesaplanıyor...",
    "transaction": "İşlem önerisi hazırlanıyor...",
    "handoff": "Yanıt hazırlanıyor...",
    # Etiketi olmayan bir düğüm hiç ilerleme olayı yayınlamıyor (`if label:`),
    # yani kullanıcı akışta boşluk görürdü.
    "sources_recap": "Önceki kaynaklar toplanıyor...",
    "synthesis": "Yanıt yazılıyor...",
    "compliance_gate": "Uygunluk kontrolü yapılıyor...",
}


async def run_turn_streaming(
    user_message: str,
    user_id: str = "anonymous",
    conversation_history: Optional[list[dict[str, str]]] = None,
    thread_id: str = "default",
):
    """Yield ("stage", label) as each node completes, then ("state", final).

    Only the STAGES stream. The answer itself is emitted once, after the
    compliance gate has passed it.

    That ordering is the whole point. The graph is
    router -> specialist -> synthesis -> compliance_gate, and it is
    fail-closed: a draft that compliance BLOCKs must never reach the user.
    Streaming synthesis tokens as they were generated would put text on screen
    that the gate might then retract, so the guarantee would hold only until
    the first block. The client gets real progress while the turn runs and
    types out the APPROVED text afterwards.
    """
    agent_trace.new_turn(thread_id)
    state = _initial_state(user_message, user_id, conversation_history)
    # Seeded from the initial state, not empty: `updates` mode yields only the
    # keys a node returned, so `user_message` and friends would be missing
    # from the accumulated result that widgets.build() reads.
    final: dict[str, Any] = dict(state)
    async for update in get_graph().astream(
        state, config=_graph_config(thread_id), stream_mode="updates"
    ):
        for node, patch in (update or {}).items():
            if isinstance(patch, dict):
                final.update(patch)
            label = STAGE_LABELS_TR.get(node)
            if label:
                yield "stage", label
    yield "state", final


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _history_summary(state: MoneyFastState) -> Optional[str]:
    """The conversation as a flat transcript.

    Not a summary despite the name: no model is asked to condense anything,
    which is deliberate -- a generated summary is one more surface that can
    invent a figure, and this text feeds the router's coreference resolution.

    The character cap slices the TAIL, so when it bites it is the oldest turn
    that loses its opening rather than the newest turn losing its end.
    """
    history = state.get("conversation_history") or []
    if not history:
        return None
    lines = []
    for turn in history[-HISTORY_MAX_TURNS:]:
        role = turn.get("role", "user")
        content = str(turn.get("content", ""))
        if role == "assistant":
            # Excerpt, not transcript. A whole previous answer sitting in the
            # prompt is a template, and synthesis copied one: asked for
            # THYAO's price with a valid THYAO payload in hand, it reproduced
            # the previous turn's "ASELS verisi alınamadı" word for word.
            # Coreference needs the SUBJECT of the last answer, never its
            # body, so the body is the part that goes.
            content = _excerpt(content)
            lines.append(f"[önceki yanıt özeti] {content}")
        else:
            lines.append(f"kullanıcı: {content}")
    return "\n".join(lines)[-HISTORY_MAX_CHARS:]


def _excerpt(content: str) -> str:
    """First sentence-ish of an assistant turn, enough to name its subject."""
    flat = " ".join(content.split())
    if len(flat) <= HISTORY_ANSWER_EXCERPT_CHARS:
        return flat
    return flat[:HISTORY_ANSWER_EXCERPT_CHARS].rstrip() + "…"


def _specialist_task(state: MoneyFastState) -> str:
    return json.dumps(
        {
            "task": state["user_message"],
            "primary_intent": state.get("primary_intent"),
            "entities": state.get("entities") or {},
            "user_id": state.get("user_id"),
            "conversation_summary": _history_summary(state),
        },
        ensure_ascii=False,
    )


#: Substrings identifying an error the CALLER can fix by rewriting its
#: arguments, as opposed to one the caller can do nothing about (backend down,
#: timeout). Only the former is worth a second attempt.
#: "is not one of" is how the risk tools word a rejected lookback, and like
#: the others it is followed by the permitted values -- which is the whole
#: reason a repair attempt is worth making rather than a re-roll.
_REPAIRABLE_MARKERS = (
    "unrecognised", "unrecognized", "invalid", "allowed:", "is not one of",
)


def _is_repairable(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _REPAIRABLE_MARKERS)


async def _repair_args(
    state: MoneyFastState, prompt: str, args: dict[str, Any], error: str
) -> Optional[dict[str, Any]]:
    """Ask the planner to fix arguments the tool rejected.

    The tool's own error names the permitted values, so the model is being
    corrected with the authoritative list rather than asked to guess again.
    Returns None if the retry produced nothing usable.
    """
    task = json.dumps(
        {
            "task": state["user_message"],
            "rejected_arguments": args,
            "tool_error": error,
            "instruction": (
                "The tool rejected these arguments. Re-emit the SAME envelope with "
                "only the offending value corrected to one the error permits. Do not "
                "change the user's intent and do not drop a filter to make it pass."
            ),
        },
        ensure_ascii=False,
    )
    try:
        plan = await _llm_json(prompt, task, fast=True)
    except Exception as exc:  # pragma: no cover - defensive, retry is best-effort
        log.warning("argument repair failed: %s", exc)
        return None
    repaired = plan.get("arguments") or None
    if not repaired:
        return None
    # Compare on the merged form: the node adds defaults (top_k) after the
    # planner runs, so a repair that changed nothing still looks different
    # from the arguments actually sent. Re-sending those would fail
    # identically and cost another round trip.
    merged = {**args, **repaired}
    return merged if merged != args else None


#: Verb forms that state a direction, matched on whole words.
#:
#: Curated forms rather than a prefix like `al*`, because in this domain `al*`
#: also matches **altın** (gold) — "altın fiyatı ne kadar" would read as a buy
#: order. `sat*` is safer but still needs `satın` carved out, since "satın al"
#: is a purchase that contains the sell stem.
_SELL_FORMS = (
    "satsana", "satsanıza", "satalım", "satayım", "satacağım", "satacagim",
    "satıcam", "saticam", "satmak", "satıyorum", "satiyorum", "satabilir",
    "satar", "satış", "satis", "satın", "sat", "bozdur", "bozdurayım",
)
_BUY_FORMS = (
    "alsana", "alsanıza", "alayım", "alalım", "alacağım", "alacagim",
    "alıcam", "alicam", "almak", "alıyorum", "aliyorum", "alabilir",
    "alırım", "alirim", "alım", "alim", "al",
)
_SELL_PHRASES = ("elden çıkar", "elden cikar", "nakde çevir", "nakde cevir")
_BUY_PHRASES = ("satın al", "satin al")


def _fold(text: str) -> str:
    """Lowercase with Turkish dotted/dotless i folded together.

    `str.lower()` leaves "İ" intact on some inputs and maps "I" to "i" rather
    than "ı", and users type both. Folding here keeps the verb match from
    depending on which keyboard produced the message.
    """
    table = str.maketrans({"İ": "i", "I": "ı", "Î": "i"})
    return text.translate(table).lower()


def _has_word(folded: str, forms: tuple[str, ...]) -> bool:
    """Whole-word match, so "al" does not fire inside "altın" or "alan"."""
    return any(re.search(rf"(?<!\w){re.escape(form)}(?!\w)", folded) for form in forms)


def _stated_direction(message: str) -> Optional[str]:
    """BUY / SELL when the user's own words say so, else None.

    "satın al" is checked first because it contains "sat": without that, every
    purchase phrased that way would read as a sale.
    """
    folded = _fold(message or "")
    if any(phrase in folded for phrase in _BUY_PHRASES):
        return "BUY"
    if any(phrase in folded for phrase in _SELL_PHRASES):
        return "SELL"
    if _has_word(folded, _SELL_FORMS):
        return "SELL"
    if _has_word(folded, _BUY_FORMS):
        return "BUY"
    return None


#: Turkish ways of saying "not that one", as they appear right after the
#: instrument: "THYAO değil", "thyao istemiyorum", "onu yerine".
_REFUSAL_MARKERS = (
    "değil", "degil", "istemiyorum", "istemem", "olmasın", "olmasin",
    "vazgeçtim", "vazgectim", "yerine",
)


def _same_instrument(token: str, symbol: str) -> bool:
    """Ticker and company name for one instrument: ASELS / aselsan."""
    if token == symbol:
        return True
    if len(token) >= 4 and len(symbol) >= 4:
        return token.startswith(symbol) or symbol.startswith(token)
    return False


def _symbol_refused_in_message(
    state: MoneyFastState, args: dict[str, Any]
) -> Optional[str]:
    """Return the symbol when THIS turn rejected the one being staged.

    The prompt already forbids it, and the prompt was not enough: asked for
    "thyao değil diğer bahsettiğim hisseyi satın alacağım", the planner staged
    THYAO. A rule that decides where money goes belongs in code, the same way
    the direction check and the crisis resources do -- a sampled token is not
    a control.

    Narrow on purpose: it fires only when the refusal word follows the symbol
    closely, so "ASELS al, THYAO değil" blocks THYAO and leaves ASELS alone.
    """
    symbol = ((args.get("instrument") or {}).get("symbol") or "").strip().casefold()
    if not symbol:
        return None

    tokens = re.findall(r"[0-9a-zçğıöşü]+", (state.get("user_message") or "").casefold())
    for index, token in enumerate(tokens):
        if not _same_instrument(token, symbol):
            continue
        # Two tokens, not more. At three, "asels al, thyao değil" reached the
        # "değil" belonging to THYAO and refused the instrument the user had
        # just asked for.
        for follower in tokens[index + 1 : index + 3]:
            if any(follower.startswith(marker) for marker in _REFUSAL_MARKERS):
                return (args.get("instrument") or {}).get("symbol")
    return None


def _direction_contradicts_message(
    state: MoneyFastState, args: dict[str, Any]
) -> Optional[str]:
    """The planner's direction against the user's verb.

    "10 tane aselsan satsana" was staged as a BUY and settled. The prompt now
    names the verbs, but a prompt is guidance; this is the check. It also
    matters that a flipped direction SKIPS the sell-side inventory guard in the
    backend and lands in the cash check instead, so the mistake surfaces as a
    successful purchase rather than an error.

    Returns None when the user stated no direction — inferring one from history
    is exactly the failure being prevented, so an unstated direction is left to
    the tool's own validation.
    """
    stated = _stated_direction(state.get("user_message") or "")
    if stated is None:
        return None
    emitted = str(args.get("transaction_type") or "").upper()
    if emitted in ("BUY", "ALIS", "ALIŞ"):
        emitted = "BUY"
    elif emitted in ("SELL", "SATIS", "SATIŞ"):
        emitted = "SELL"
    else:
        return None
    return None if emitted == stated else f"{emitted}!={stated}"


def _amount_not_in_current_turn(
    state: MoneyFastState, args: dict[str, Any]
) -> Optional[str]:
    """Return the offending figure when this turn's own number was overruled.

    Guards the 250/200 bug: the user said "250 adet alacaktım" earlier, says
    "200 adet al" now, and the planner stages 250 -- a figure the user has
    just replaced. That is the case worth blocking, and the signal for it is
    specific: THIS message states a number, and the planner used a different
    one that it found in the history.

    It deliberately does NOT fire when this message names no figure at all.
    "son söylediğim adet kadar al" is the user explicitly delegating to the
    history, and refusing it produced a loop with no exit: the planner
    resolved quantity=2 correctly, the guard rejected it, the assistant asked
    again, and the user answered "birkaç mesaj önce söyledim" four times
    before giving up. Carrying the figure forward there is what was asked
    for, it is surfaced as an assumption, and it still cannot move money
    without the on-screen confirmation.
    """
    message = (state.get("user_message") or "").replace(".", "").replace(",", "")
    stated_here = set(re.findall(r"\d+(?:\.\d+)?", message))
    if not stated_here:
        # No competing figure in this turn: nothing was overruled.
        return None

    history = " ".join(
        str(turn.get("content", "")) for turn in (state.get("conversation_history") or [])
    ).replace(".", "").replace(",", "")

    candidates: list[tuple[str, float]] = []
    quantity = args.get("quantity")
    if isinstance(quantity, (int, float)):
        candidates.append(("quantity", float(quantity)))
    notional = args.get("notional_amount")
    if isinstance(notional, dict) and isinstance(notional.get("amount"), (int, float)):
        candidates.append(("notional_amount", float(notional["amount"])))

    for field, value in candidates:
        # Compare as the user would have typed it: "250" not "250.0".
        written = str(int(value)) if float(value).is_integer() else str(value)
        if written not in stated_here and written in history:
            return f"{field}={written}"
    return None


async def _run_tool(
    state: MoneyFastState,
    tool: str,
    args: dict[str, Any],
    assumptions: Optional[list[str]] = None,
    empty_when=None,
    repair_prompt: Optional[str] = None,
) -> dict[str, Any]:
    try:
        payload = await get_mcp_client().call(tool, args)
    except (MCPUnavailable, MCPToolError) as exc:
        # One correction attempt, and only for an error the arguments can fix.
        # Without it a single unrecognised enum value became "Verilere
        # ulaşamadım" and the user had to type "tekrar dene" to re-roll the
        # planner into a legal value.
        if repair_prompt and _is_repairable(exc):
            repaired = await _repair_args(state, repair_prompt, args, str(exc))
            if repaired is not None:
                log.info("retrying %s with repaired arguments", tool)
                try:
                    payload = await get_mcp_client().call(tool, repaired)
                except (MCPUnavailable, MCPToolError) as retry_exc:
                    return _tool_error(state, tool, retry_exc)
                else:
                    return _tool_success(state, tool, payload, assumptions, empty_when)
        return _tool_error(state, tool, exc)

    return _tool_success(state, tool, payload, assumptions, empty_when)


def _tool_success(
    state: MoneyFastState,
    tool: str,
    payload: Any,
    assumptions: Optional[list[str]],
    empty_when,
) -> dict[str, Any]:
    status = "EMPTY" if (empty_when and empty_when(payload)) else "OK"
    return {
        "specialist_output": {
            "agent": state.get("target_agent"),
            "status": status,
            "tool": tool,
            "data": payload,
            "assumptions": assumptions or [],
        },
        "tools_used": (state.get("tools_used") or []) + [tool],
    }


def _tool_error(state: MoneyFastState, tool: str, exc: Exception) -> dict[str, Any]:
    log.error("tool %s failed: %s", tool, exc)
    return {
        "specialist_output": {
            "agent": state.get("target_agent"),
            "status": "ERROR",
            "tool": tool,
            "data": None,
            "error": str(exc),
            "instruction": DATA_FAILURE_TR,
        },
        "errors": (state.get("errors") or []) + [f"{tool}: {exc}"],
    }


def _disclosure_texts(verdict: dict[str, Any]) -> list[str]:
    """The disclosures this turn requires, as separate strings.

    Returned alongside the answer rather than concatenated into it. The words
    are unchanged and still mandatory; only their placement moves, so the chat
    can render them as a footnote instead of three sentences of boilerplate
    glued to a one-line reply.
    """
    out: list[str] = []
    for item in verdict.get("required_disclosures") or []:
        body = (item.get("text") or "").strip()
        if body and body not in out:
            out.append(body)
    return out


def _without_disclosures(text: str, verdict: dict[str, Any]) -> str:
    """Remove disclosure sentences the compliance layer appended to the draft.

    The backend's `remediated_response` arrives with them already inlined. They
    are carried structurally instead, so leaving the copies in the prose would
    show each notice twice.
    """
    cleaned = text
    for body in _disclosure_texts(verdict):
        cleaned = cleaned.replace(body, "")
    # Collapse the blank lines the removals leave behind.
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _with_disclosures(text: str, verdict: dict[str, Any]) -> str:
    """Insert required disclosures verbatim. Never paraphrase them."""
    prepend, append = [], []
    for item in verdict.get("required_disclosures") or []:
        body = (item.get("text") or "").strip()
        if not body or body in text:
            continue
        (prepend if item.get("placement") == "PREPEND" else append).append(body)
    return "\n\n".join([*prepend, text, *append]).strip()


def _idempotency_key(state: MoneyFastState) -> str:
    """One key per turn.

    The seed used to include `len(conversation_history)`, which is bounded by
    the window. Once the window saturates the length stops changing, so asking
    the same thing twice produced the SAME key and the second, legitimate
    staging request could be deduplicated into the first proposal.

    The turn's trace id is unique per turn and stable across the graph's own
    argument-repair retry -- which is the retry idempotency exists for.
    """
    import hashlib

    trace_id = agent_trace.current_trace_id() or ""
    seed = f"{state.get('user_id')}|{state['user_message']}|{trace_id}"
    return "idem_" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
async def _repl() -> None:
    print("MoneyFast orchestrator. Boş satır ile çıkın.\n")
    history: list[dict[str, str]] = []
    while True:
        try:
            message = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not message:
            break
        result = await run_turn(message, user_id="u_local", conversation_history=history)
        print("\n" + (result.get("final_output") or GENERIC_FAILURE_TR) + "\n")
        history.append({"role": "user", "content": message})
        history.append({"role": "assistant", "content": result.get("final_output") or ""})


if __name__ == "__main__":
    if len(sys.argv) > 1:
        out = asyncio.run(run_turn(" ".join(sys.argv[1:]), user_id="u_local"))
        print(out.get("final_output") or GENERIC_FAILURE_TR)
    else:
        asyncio.run(_repl())
