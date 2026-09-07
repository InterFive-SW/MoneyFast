"""`get_portfolio_news` birim testleri — sözleşme v2.11.

Araç, sahiplik ile haber etiketinin KESİŞİMİNİ döndürüyor. Buradaki en önemli
iddialar üç tanesi:

* sıfır bir ÖLÇÜMDÜR. "O hisse hakkında bu pencerede bir şey yayımlanmadı" ile
  "veri gelmedi" karşıt iddialar, ve ajana sıfırı ilkiymiş gibi anlatması
  söyleniyor;
* pencere yanıtta taşınıyor. Penceresiz bir "haber yok", tüm tarih hakkında bir
  iddia olurdu ve bu araç tüm tarihe hiç bakmadı;
* yanıtta yorum yok. Duygu, önem, sıralama alanı YOK -- bir başlığın iyi ya da
  kötü olduğu bir piyasa görüşü ve bu sistemin görüş tutma izni yok.
"""

from __future__ import annotations

import pytest

import news_tools
from backend_client import ContractViolationError, UpstreamUnavailableError

TOOL_KEYS = {"window_days", "holdings", "articles"}
HOLDING_KEYS = {"symbol", "name", "news_count"}
ARTICLE_KEYS = {
    "id", "title", "source", "url", "published_at",
    "held_symbols", "related_symbols",
}


def body(**overrides):
    """Backend'in sağlıklı yanıtı — arayüzün okuduğu camelCase gövde."""
    payload = {
        "symbols": [
            {"symbol": "AKBNK", "name": "Akbank T.A.Ş.", "count": 2},
            {"symbol": "DOAS", "name": "Doğuş Otomotiv", "count": 0},
        ],
        "items": [
            {
                "id": "n1",
                "source": "Patronlar Dünyası - Finans",
                "title": "Akbank'tan yılın ilk yarısında ekonomiye 2,9 trilyon lira",
                "url": "https://example.invalid/n1",
                "time": "3 gün önce",
                "publishedAt": "2026-08-29T08:10:00Z",
                "sentiment": "neutral",
                "relatedSymbols": ["AKBNK", "THYAO"],
                "heldSymbols": ["AKBNK"],
            }
        ],
        "windowDays": 90,
    }
    payload.update(overrides)
    return payload


class TestContract:
    @pytest.mark.asyncio
    async def test_top_level_keys_match_v211_exactly(self, fake_backend):
        fake_backend.json("portfolio_news", body())
        payload = await news_tools.get_portfolio_news("u_1")
        assert set(payload) == TOOL_KEYS

    @pytest.mark.asyncio
    async def test_holding_and_article_keys_match_v211_exactly(self, fake_backend):
        fake_backend.json("portfolio_news", body())
        payload = await news_tools.get_portfolio_news("u_1")
        assert set(payload["holdings"][0]) == HOLDING_KEYS
        assert set(payload["articles"][0]) == ARTICLE_KEYS

    @pytest.mark.asyncio
    async def test_no_sentiment_field_survives_the_boundary(self, fake_backend):
        """Backend `sentiment: neutral` gönderiyor ve bu alan araca GEÇMİYOR.
        Taşınsaydı model onu bir sınıflandırma sanıp "nötr haberler" derdi."""
        fake_backend.json("portfolio_news", body())
        payload = await news_tools.get_portfolio_news("u_1")
        assert "sentiment" not in payload["articles"][0]

    @pytest.mark.asyncio
    async def test_the_user_travels_in_the_path(self, fake_backend):
        fake_backend.json("portfolio_news", body())
        await news_tools.get_portfolio_news("u_42")
        assert "/market/news/portfolio/u_42" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_it_carries_no_market_data_fields(self, fake_backend):
        """`as_of`/`source`/`is_delayed` bu aracın alanları değil: her haberin
        kendi yayım tarihi var ve "gecikmeli" bir haber diye bir şey yok."""
        from conftest import assert_no_market_data_fields

        fake_backend.json("portfolio_news", body())
        assert_no_market_data_fields(await news_tools.get_portfolio_news("u_1"))


class TestGuards:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("missing", ["symbols", "items", "windowDays"])
    async def test_a_missing_top_level_key_is_a_contract_violation(
        self, fake_backend, missing
    ):
        payload = body()
        del payload[missing]
        fake_backend.json("portfolio_news", payload)
        with pytest.raises(ContractViolationError):
            await news_tools.get_portfolio_news("u_1")

    @pytest.mark.asyncio
    async def test_a_holding_without_a_count_is_refused(self, fake_backend):
        """Eksik sayıyı sıfıra düşürmek, ölçülmüş bir "hiçbir şey yayımlanmadı"
        ile "sayı gelmedi"yi aynı şey yapardı."""
        fake_backend.json(
            "portfolio_news", body(symbols=[{"symbol": "AKBNK", "name": "Akbank"}])
        )
        with pytest.raises(ContractViolationError):
            await news_tools.get_portfolio_news("u_1")

    @pytest.mark.asyncio
    async def test_an_article_without_a_date_is_refused(self, fake_backend):
        """Ajana başlığı kaynağı ve tarihiyle aktarması söyleniyor; tarihi
        olmayan bir başlık yine de tarihlenirdi."""
        article = body()["items"][0]
        del article["publishedAt"]
        fake_backend.json("portfolio_news", body(items=[article]))
        with pytest.raises(ContractViolationError):
            await news_tools.get_portfolio_news("u_1")

    @pytest.mark.asyncio
    async def test_a_non_object_holding_is_refused(self, fake_backend):
        fake_backend.json("portfolio_news", body(symbols=["AKBNK"]))
        with pytest.raises(ContractViolationError):
            await news_tools.get_portfolio_news("u_1")

    @pytest.mark.asyncio
    async def test_a_non_object_article_is_refused(self, fake_backend):
        fake_backend.json("portfolio_news", body(items=["haber"]))
        with pytest.raises(ContractViolationError):
            await news_tools.get_portfolio_news("u_1")

    @pytest.mark.asyncio
    async def test_a_non_list_symbols_block_is_refused(self, fake_backend):
        fake_backend.json("portfolio_news", body(symbols={"AKBNK": 2}))
        with pytest.raises(ContractViolationError):
            await news_tools.get_portfolio_news("u_1")

    @pytest.mark.asyncio
    async def test_an_unreachable_backend_raises_rather_than_reporting_no_news(
        self, fake_backend, no_sleep
    ):
        """Ulaşılamayan bir servis boş bir sonuç DEĞİLDİR. "Haber yok" demek,
        bakılmamış bir pencere hakkında bir iddia olurdu."""
        fake_backend.fail("portfolio_news")
        with pytest.raises(UpstreamUnavailableError):
            await news_tools.get_portfolio_news("u_1")


class TestAbsence:
    @pytest.mark.asyncio
    async def test_a_quiet_holding_is_reported_as_zero_not_dropped(self, fake_backend):
        fake_backend.json("portfolio_news", body())
        payload = await news_tools.get_portfolio_news("u_1")
        assert [(h["symbol"], h["news_count"]) for h in payload["holdings"]] == [
            ("AKBNK", 2), ("DOAS", 0)
        ]

    @pytest.mark.asyncio
    async def test_nothing_matched_still_names_the_window(self, fake_backend):
        fake_backend.json("portfolio_news", body(items=[], symbols=[]))
        payload = await news_tools.get_portfolio_news("u_1")
        assert payload["articles"] == []
        assert payload["window_days"] == 90

    @pytest.mark.asyncio
    async def test_a_holding_without_a_name_falls_back_to_its_symbol(self, fake_backend):
        fake_backend.json("portfolio_news", body(symbols=[{"symbol": "AKBNK", "count": 0}]))
        payload = await news_tools.get_portfolio_news("u_1")
        assert payload["holdings"][0]["name"] == "AKBNK"

    @pytest.mark.asyncio
    async def test_an_article_without_a_link_is_an_empty_string(self, fake_backend):
        article = body()["items"][0]
        article["url"] = None
        fake_backend.json("portfolio_news", body(items=[article]))
        payload = await news_tools.get_portfolio_news("u_1")
        assert payload["articles"][0]["url"] == ""

    @pytest.mark.asyncio
    async def test_held_symbols_says_why_the_article_is_listed(self, fake_backend):
        """Haber iki şirketi anıyor; kullanıcı yalnızca birine sahip."""
        fake_backend.json("portfolio_news", body())
        article = (await news_tools.get_portfolio_news("u_1"))["articles"][0]
        assert article["held_symbols"] == ["AKBNK"]
        assert article["related_symbols"] == ["AKBNK", "THYAO"]

    @pytest.mark.asyncio
    async def test_missing_symbol_lists_become_empty_not_absent(self, fake_backend):
        article = body()["items"][0]
        del article["heldSymbols"]
        del article["relatedSymbols"]
        fake_backend.json("portfolio_news", body(items=[article]))
        payload = await news_tools.get_portfolio_news("u_1")
        assert payload["articles"][0]["held_symbols"] == []
        assert payload["articles"][0]["related_symbols"] == []


class TestArguments:
    @pytest.mark.asyncio
    async def test_the_default_limit_is_applied(self, fake_backend):
        fake_backend.json("portfolio_news", body())
        await news_tools.get_portfolio_news("u_1")
        assert f"limit={news_tools.DEFAULT_LIMIT}" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_a_null_limit_means_no_preference(self, fake_backend):
        """Model, hakkında görüşü olmayan bir parametre için düzenli olarak
        `null` yolluyor; bunu geçersiz saymak turu düşürürdü."""
        fake_backend.json("portfolio_news", body())
        await news_tools.get_portfolio_news("u_1", limit=None)
        assert f"limit={news_tools.DEFAULT_LIMIT}" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "asked,sent", [(0, news_tools.MIN_LIMIT), (500, news_tools.MAX_LIMIT), (5, 5)]
    )
    async def test_the_limit_is_clamped(self, fake_backend, asked, sent):
        fake_backend.json("portfolio_news", body())
        await news_tools.get_portfolio_news("u_1", limit=asked)
        assert f"limit={sent}" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_no_window_is_sent_unless_the_caller_named_one(self, fake_backend):
        """Backend'in penceresi Analiz ekranının da penceresi. Buraya bir sayı
        gömmek, sohbetin ve ekranın "haber yok"un neyi kapsadığı konusunda
        ayrışması demekti."""
        fake_backend.json("portfolio_news", body())
        await news_tools.get_portfolio_news("u_1")
        assert "days=" not in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_a_named_period_is_forwarded(self, fake_backend):
        fake_backend.json("portfolio_news", body())
        await news_tools.get_portfolio_news("u_1", days=7)
        assert "days=7" in str(fake_backend.last.url)


class TestRegistration:
    def test_the_tool_is_attached_to_the_server(self):
        registered = []
        news_tools.register(
            type("FakeMCP", (), {"tool": lambda self: registered.append})()
        )
        assert registered == [
            news_tools.get_portfolio_news,
            news_tools.get_news_impact_digest,
        ]


# ── get_news_impact_digest (v2.23) ─────────────────────────────────────────
#
# Bu araç sistemdeki tek araç ki taşıdığı şey bir ÖLÇÜM DEĞİL, bir modelin
# metin okuması. Buradaki en önemli üç iddia:
#
# * `disclaimer` ZORUNLU ve varsayılanı YOK. Varsayılan, cümlenin ikinci bir
#   kopyası olurdu ve sunucudaki metin değiştikten sonra da çalışmaya devam
#   ederek sessizce eskimiş bir çekince yayınlardı;
# * `counts` DIŞARI ÇIKMIYOR. Ajana "sıralama yapma" deniyor ve ham bir sayım
#   tam olarak bunun malzemesi -- alanı göndermemek, kullanımını yasaklamaktan
#   güçlü;
# * ölçülemeyen hareket `null` kalıyor, sıfır olmuyor.

DIGEST_KEYS = {"window_hours", "headline", "disclaimer", "entries"}
ENTRY_KEYS = {"symbol", "sentence", "reasons"}
REASON_KEYS = {"news_id", "mechanism", "published_at"}


def digest_body(**overrides):
    payload = {
        "headline": "Son 24 saatte portföyünüzdeki 1 enstrüman haberlere konu oldu.",
        "entries": [
            {
                "symbol": "ASELS",
                "sentence": "ASELS: 2 haber yorumu, yükseliş yönünde okundu.",
                "counts": {"UP": 2, "DOWN": 0, "NEUTRAL": 0},
                "directCount": 2,
                "spilloverCount": 0,
                "measured": {"typicalMovePct": 3.1, "recentMovePct": 1.2},
                "reasons": [
                    {
                        "newsId": "n1",
                        "direction": "UP",
                        "scope": "DIRECT",
                        "magnitude": "HIGH",
                        "mechanism": "Sözleşme tutarı yıllık ihracata ekleniyor.",
                        "publishedAt": "2026-09-07T10:00:00Z",
                    }
                ],
            }
        ],
        "windowHours": 24,
        "disclaimer": "Bu özet, haber metinlerinin yapay zeka tarafından yorumlanmasıdır.",
    }
    payload.update(overrides)
    return payload


class TestDigestContract:
    @pytest.mark.asyncio
    async def test_top_level_keys_match_v223_exactly(self, fake_backend):
        fake_backend.json("news_digest", digest_body())
        payload = await news_tools.get_news_impact_digest("u_1")
        assert set(payload) == DIGEST_KEYS

    @pytest.mark.asyncio
    async def test_entry_and_reason_keys_are_frozen(self, fake_backend):
        fake_backend.json("news_digest", digest_body())
        payload = await news_tools.get_news_impact_digest("u_1")
        assert set(payload["entries"][0]) == ENTRY_KEYS
        assert set(payload["entries"][0]["reasons"][0]) == REASON_KEYS

    @pytest.mark.asyncio
    async def test_the_tally_never_leaves_the_backend(self, fake_backend):
        """Ajana sıralama yapmaması söyleniyor; ham sayım tam bunun
        malzemesi. Alanı göndermemek, kullanımını yasaklamaktan güçlü."""
        fake_backend.json("news_digest", digest_body())
        payload = await news_tools.get_news_impact_digest("u_1")
        assert "counts" not in payload["entries"][0]

    @pytest.mark.asyncio
    async def test_the_raw_enums_never_leave_the_backend(self, fake_backend):
        """Ölçüldü: payload'da dururken model satırları kendi
        "Artış lehine / Düşüş lehine" başlıkları altında yeniden grupladı ve
        enum'ları düz yazıya döktü ("yönü DOWN olarak işaretlendi",
        "(spil-over)"). İkisi de zaten cümlede Türkçe yazılı."""
        fake_backend.json("news_digest", digest_body())
        payload = await news_tools.get_news_impact_digest("u_1")
        reason = payload["entries"][0]["reasons"][0]
        assert "direction" not in reason and "scope" not in reason

    @pytest.mark.asyncio
    async def test_the_declared_confidence_never_leaves_the_backend(self, fake_backend):
        """Modelin kendi beyanı bir ölçüm değil."""
        fake_backend.json("news_digest", digest_body())
        payload = await news_tools.get_news_impact_digest("u_1")
        assert "confidence" not in payload["entries"][0]["reasons"][0]

    @pytest.mark.asyncio
    async def test_the_sentence_is_relayed_unchanged(self, fake_backend):
        fake_backend.json("news_digest", digest_body())
        payload = await news_tools.get_news_impact_digest("u_1")
        assert payload["entries"][0]["sentence"] == \
            "ASELS: 2 haber yorumu, yükseliş yönünde okundu."

    @pytest.mark.asyncio
    async def test_a_missing_disclaimer_is_a_contract_violation(self, fake_backend):
        """Varsayılan bir çekince, sunucudaki metin değiştikten sonra da
        çalışmaya devam eden sessizce eskimiş bir kopya olurdu."""
        payload = digest_body()
        payload.pop("disclaimer")
        fake_backend.json("news_digest", payload)
        with pytest.raises(ContractViolationError):
            await news_tools.get_news_impact_digest("u_1")

    @pytest.mark.asyncio
    async def test_a_missing_headline_is_a_contract_violation(self, fake_backend):
        payload = digest_body()
        payload.pop("headline")
        fake_backend.json("news_digest", payload)
        with pytest.raises(ContractViolationError):
            await news_tools.get_news_impact_digest("u_1")

    @pytest.mark.asyncio
    async def test_a_non_object_entry_is_refused(self, fake_backend):
        fake_backend.json("news_digest", digest_body(entries=["ASELS"]))
        with pytest.raises(ContractViolationError):
            await news_tools.get_news_impact_digest("u_1")

    @pytest.mark.asyncio
    async def test_an_entry_without_a_sentence_is_refused(self, fake_backend):
        """Cümle backend'de kuruluyor; olmadığında ajanın kuracağı cümle
        koşulsuz olurdu."""
        fake_backend.json("news_digest", digest_body(entries=[
            {"symbol": "ASELS", "reasons": []}]))
        with pytest.raises(ContractViolationError):
            await news_tools.get_news_impact_digest("u_1")

    @pytest.mark.asyncio
    async def test_a_non_object_reason_is_refused(self, fake_backend):
        entry = digest_body()["entries"][0]
        entry["reasons"] = ["sebep"]
        fake_backend.json("news_digest", digest_body(entries=[entry]))
        with pytest.raises(ContractViolationError):
            await news_tools.get_news_impact_digest("u_1")

    @pytest.mark.asyncio
    async def test_a_reason_without_a_direction_is_still_refused(self, fake_backend):
        """Taşınmıyor ama ZORUNLU: eksikse backend'in gövdesi bozuk demektir
        ve bozuk bir gövdeden okunan mekanizmaya da güvenilmez."""
        entry = digest_body()["entries"][0]
        entry["reasons"][0].pop("direction")
        fake_backend.json("news_digest", digest_body(entries=[entry]))
        with pytest.raises(ContractViolationError):
            await news_tools.get_news_impact_digest("u_1")

    @pytest.mark.asyncio
    async def test_a_reason_without_a_news_id_is_refused(self, fake_backend):
        """Kaynağına kadar izlenemeyen bir iddia, kullanıcının
        doğrulayamayacağı bir iddiadır."""
        entry = digest_body()["entries"][0]
        entry["reasons"][0].pop("newsId")
        fake_backend.json("news_digest", digest_body(entries=[entry]))
        with pytest.raises(ContractViolationError):
            await news_tools.get_news_impact_digest("u_1")


class TestDigestWithholding:
    """Taşınmayan alanlar. Hepsi cümlenin İÇİNDE zaten Türkçe yazılı ve
    hepsi, yazarın tabloya çevirdiği şekil."""

    @pytest.mark.asyncio
    async def test_the_measured_move_never_leaves_the_backend(self, fake_backend):
        """Ölçüldü: payload'da dururken model beş satırlık bir fiyat tablosu
        kurdu ve TEK BİR mekanizma yazmadı -- haberin ne anlama geldiğine dair
        bir cevap, içinde haber olmadan. Sayılar cümlede zaten var."""
        fake_backend.json("news_digest", digest_body())
        payload = await news_tools.get_news_impact_digest("u_1")
        assert "measured" not in payload["entries"][0]

    @pytest.mark.asyncio
    async def test_the_scope_counts_never_leave_the_backend(self, fake_backend):
        fake_backend.json("news_digest", digest_body())
        entry = payload_entry = (await news_tools.get_news_impact_digest("u_1"))[
            "entries"][0]
        assert "direct_count" not in entry and "spillover_count" not in entry
        assert entry is payload_entry

    @pytest.mark.asyncio
    async def test_the_sentence_still_carries_the_numbers(self, fake_backend):
        """Alanı düşürmek sayıyı düşürmek DEĞİL: ölçüm cümlenin içinde."""
        entry = digest_body()["entries"][0]
        entry["sentence"] += " Ölçülen: hisse son 5 işlem gününde %1,20 yükseldi."
        fake_backend.json("news_digest", digest_body(entries=[entry]))
        payload = await news_tools.get_news_impact_digest("u_1")
        assert "%1,20" in payload["entries"][0]["sentence"]


class TestDigestWindow:
    @pytest.mark.asyncio
    async def test_the_default_window_matches_the_screen(self, fake_backend):
        fake_backend.json("news_digest", digest_body())
        await news_tools.get_news_impact_digest("u_1")
        assert "hours=24" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_a_named_window_is_carried(self, fake_backend):
        fake_backend.json("news_digest", digest_body())
        await news_tools.get_news_impact_digest("u_1", hours=72)
        assert "hours=72" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_an_oversized_window_is_clamped(self, fake_backend):
        fake_backend.json("news_digest", digest_body())
        await news_tools.get_news_impact_digest("u_1", hours=99999)
        assert f"hours={news_tools.MAX_HOURS}" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_a_zero_window_is_clamped_up(self, fake_backend):
        fake_backend.json("news_digest", digest_body())
        await news_tools.get_news_impact_digest("u_1", hours=0)
        assert f"hours={news_tools.MIN_HOURS}" in str(fake_backend.last.url)

    @pytest.mark.asyncio
    async def test_the_user_is_named_in_the_path(self, fake_backend):
        fake_backend.json("news_digest", digest_body())
        await news_tools.get_news_impact_digest("u_42")
        assert "/market/news/digest/u_42" in str(fake_backend.last.url)


class TestDigestUpstream:
    @pytest.mark.asyncio
    async def test_an_unreachable_backend_raises(self, fake_backend):
        """Ulaşılamayan bir servis, boş bir sonuç DEĞİL."""
        fake_backend.fail("news_digest")
        with pytest.raises(UpstreamUnavailableError):
            await news_tools.get_news_impact_digest("u_1")

    @pytest.mark.asyncio
    async def test_an_empty_window_is_a_valid_answer(self, fake_backend):
        fake_backend.json("news_digest", digest_body(
            entries=[], headline="Son 24 saatte ... bulunmuyor."))
        payload = await news_tools.get_news_impact_digest("u_1")
        assert payload["entries"] == [] and payload["window_hours"] == 24
