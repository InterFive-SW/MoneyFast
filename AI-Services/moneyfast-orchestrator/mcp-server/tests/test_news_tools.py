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
        assert registered == [news_tools.get_portfolio_news]
