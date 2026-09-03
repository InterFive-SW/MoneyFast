"""Kaynak listesi.

Test edilen özellik: bir kaynak, bir aracın GERÇEKTEN döndürdüğü verinin
izdüşümüdür. Model hiçbir satırına katkıda bulunmaz. Atıflar bugüne kadar
yalnızca modelin düzyazıya koymayı seçtiği markdown bağlantılarıydı ve
ölçüldü: kullanıcı "bana kaynakça verir misin" diye sorduğunda sistem cevap
veremedi, çünkü kaynaklar hiçbir yerde veri olarak durmuyordu.
"""

from __future__ import annotations

import pytest

import sources


def state_for(agent: str, data, target: str | None = None, status: str = "OK"):
    return {
        "target_agent": agent if target is None else target,
        "specialist_output": {"agent": agent, "status": status, "data": data},
    }


def document(**over):
    row = {
        "chunk_id": "c1",
        "title": "THYAO — Pay Geri Alım İşlemleri",
        "publisher": "KAP",
        "published_at": "2026-08-28T20:15:00Z",
        "url": "https://www.kap.org.tr/tr/Bildirim/1655982",
    }
    row.update(over)
    return row


class TestDocuments:
    def test_a_retrieved_filing_becomes_a_clickable_source(self):
        out = sources.build(state_for("MARKET_RESEARCH_AGENT", {"results": [document()]}))
        assert out == [{
            "kind": "DOCUMENT",
            "label": "THYAO — Pay Geri Alım İşlemleri",
            "detail": "KAP · 2026-08-28",
            "url": "https://www.kap.org.tr/tr/Bildirim/1655982",
            "as_of": "2026-08-28T20:15:00Z",
        }]

    def test_the_publisher_stands_in_when_there_is_no_title(self):
        out = sources.build(state_for("MARKET_RESEARCH_AGENT", {"results": [document(title="")]}))
        assert out[0]["label"] == "KAP"

    def test_a_row_that_can_be_cited_by_nothing_is_dropped(self):
        """Ne başlığı ne yayıncısı olan bir satır atıf edilemez; listede
        yerinin olması, kullanıcıya tıklanamayan boş bir satır göstermek
        olurdu."""
        out = sources.build(
            state_for("MARKET_RESEARCH_AGENT", {"results": [document(title="", publisher="")]})
        )
        assert out == []

    def test_a_document_without_a_link_still_appears(self):
        out = sources.build(state_for("MARKET_RESEARCH_AGENT", {"results": [document(url=None)]}))
        assert out[0]["url"] is None and out[0]["label"]

    def test_the_same_document_from_both_passes_is_listed_once(self):
        """Dar ve geniş arama aynı belgeyi döndürebilir."""
        out = sources.build(
            state_for("MARKET_RESEARCH_AGENT", {"results": [document(), document(chunk_id="c2")]})
        )
        assert len(out) == 1

    def test_non_object_rows_are_ignored(self):
        out = sources.build(
            state_for("MARKET_RESEARCH_AGENT", {"results": [document(), "junk", None]})
        )
        assert len(out) == 1

    def test_the_list_is_capped(self):
        rows = [document(url=f"https://x/{i}", title=f"Bildirim {i}") for i in range(20)]
        assert len(sources.build(state_for("MARKET_RESEARCH_AGENT", {"results": rows}))) == 8


class TestMeasurements:
    def test_a_technical_reading_cites_its_series(self):
        out = sources.build(state_for("MARKET_DATA_AGENT", {
            "symbol": "THYAO", "as_of": "2026-09-01T00:00:00Z",
            "signals": {"observations": 252},
        }))
        assert out[0]["kind"] == "SERIES"
        assert out[0]["label"] == "THYAO günlük kapanış serisi"
        assert "252 işlem günü" in out[0]["detail"]

    def test_a_series_without_a_count_still_names_itself(self):
        out = sources.build(state_for("MARKET_DATA_AGENT", {
            "symbol": "THYAO", "as_of": "2026-09-01T00:00:00Z", "signals": {},
        }))
        assert "günlük kapanışlar" in out[0]["detail"]

    def test_a_price_screen_cites_the_quotes(self):
        out = sources.build(state_for("MARKET_DATA_AGENT", {
            "instruments": [{"symbol": "THYAO"}, {"symbol": "ASELS"}],
            "as_of": "2026-09-01T00:00:00Z",
        }))
        assert out[0]["kind"] == "QUOTE"
        assert out[0]["label"] == "2 enstrümanın son fiyatı"

    def test_the_provider_is_never_named(self):
        """`sanitize.SOURCE_REPLACEMENTS` var çünkü sağlayıcının adı 158
        cevapta yedi kez kullanıcıya ulaşmıştı. Etiket zaten 'sağlayıcı'
        diyerek kuruluyor -- sonradan temizlenmesi gereken bir şey
        üretmiyor. `sanitize` yalnızca `final_output` üzerinde çalışıyor,
        yani buraya sızan bir ad hiçbir yerde yakalanmazdı."""
        out = sources.build(state_for("MARKET_DATA_AGENT", {
            "instruments": [{"symbol": "THYAO"}], "as_of": "2026-09-01T00:00:00Z",
            "source": "YFINANCE_DELAYED",
        }))
        assert "YFINANCE" not in out[0]["detail"].upper()
        assert "sağlayıcı" in out[0]["detail"]

    def test_a_portfolio_answer_cites_the_holdings(self):
        out = sources.build(state_for("PORTFOLIO_AGENT", {
            "positions": [{"symbol": "THYAO"}, {"symbol": "ASELS"}],
            "as_of": "2026-09-01T00:00:00Z",
        }))
        assert out[0]["kind"] == "HOLDINGS"
        assert "2 pozisyon" in out[0]["detail"]

    def test_a_risk_answer_cites_the_window_and_the_questionnaire(self):
        out = sources.build(state_for("RISK_STRATEGY_AGENT", {
            "window": {"observation_count": 252}, "as_of": "2026-09-01T00:00:00Z",
            "assessed_at": "2026-07-14T09:00:00Z",
        }))
        assert [row["kind"] for row in out] == ["SERIES", "PROFILE"]

    def test_a_risk_answer_with_neither_cites_nothing(self):
        assert sources.build(state_for("RISK_STRATEGY_AGENT", {"window": "not a dict"})) == []

    def test_an_agent_with_no_measurable_source_cites_nothing(self):
        assert sources.build(state_for("TRANSACTION_AGENT", {"proposal_id": "P-1"})) == []


class TestOrdering:
    def test_documents_come_before_measurements(self):
        out = sources.build(state_for("MARKET_RESEARCH_AGENT", {
            "results": [document()],
            "positions": [{"symbol": "X"}],
        }))
        assert out[0]["kind"] == "DOCUMENT"


class TestStaleState:
    def test_a_payload_from_an_earlier_turn_is_not_cited(self):
        """Graf `thread_id` üzerinden checkpoint alıyor, yani hiç araç
        çalıştırmamış bir turda önceki turdan kalma bir çıktı durabilir.
        `widgets.build` ile aynı koruma."""
        assert sources.build(
            state_for("MARKET_RESEARCH_AGENT", {"results": [document()]},
                      target="MARKET_DATA_AGENT")
        ) == []

    def test_a_turn_that_ran_no_specialist_cites_nothing(self):
        assert sources.build({"target_agent": "EDUCATION_AGENT"}) == []

    def test_an_errored_search_still_cites_what_it_had(self):
        """`status != "OK"` kapısı BİLEREK yok. Haber araması hata verip
        kullanıcının kendi belgesi bulunduğunda elde gerçek kaynaklar var ve
        onları saklamanın sebebi yok."""
        out = sources.build(
            state_for("MARKET_RESEARCH_AGENT", {"results": [document()]}, status="ERROR")
        )
        assert len(out) == 1


class TestPriorSources:
    """Önceki turun kaynakları -- 'bana kaynakça verir misin' turunun
    gösterdiği şey."""

    def _history(self, *turns):
        return {"meta_request": "SOURCES_RECAP", "conversation_history": list(turns)}

    def test_the_newest_sourced_answer_wins(self):
        out = sources.build(self._history(
            {"role": "assistant", "sources": [{"kind": "DOCUMENT", "label": "eski"}]},
            {"role": "user", "content": "peki"},
            {"role": "assistant", "sources": [{"kind": "DOCUMENT", "label": "yeni"}]},
        ))
        assert [row["label"] for row in out] == ["yeni"]

    def test_an_answer_with_no_sources_is_skipped(self):
        out = sources.build(self._history(
            {"role": "assistant", "sources": [{"kind": "DOCUMENT", "label": "eski"}]},
            {"role": "assistant", "sources": []},
        ))
        assert [row["label"] for row in out] == ["eski"]

    def test_user_turns_are_never_read(self):
        assert sources.build(self._history(
            {"role": "user", "content": "x", "sources": [{"label": "olmaz"}]},
        )) == []

    def test_a_malformed_stored_row_is_dropped(self):
        """`meta` alanından okunuyor ve orada eski bir turdan kalma başka
        bir şekil durabilir."""
        out = sources.build(self._history(
            {"role": "assistant", "sources": ["junk", {"label": ""}, {"kind": "DOCUMENT", "label": "iyi"}]},
        ))
        assert [row["label"] for row in out] == ["iyi"]

    def test_a_conversation_with_nothing_stored_cites_nothing(self):
        assert sources.build({"meta_request": "SOURCES_RECAP"}) == []

    def test_the_recap_list_is_capped_too(self):
        rows = [{"kind": "DOCUMENT", "label": f"b{i}"} for i in range(20)]
        assert len(sources.build(self._history({"role": "assistant", "sources": rows}))) == 8


class TestPortfolioShape:
    def test_a_malformed_positions_payload_cites_nothing(self):
        assert sources.build(state_for("PORTFOLIO_AGENT", {"positions": "not a list"})) == []


class TestMarketDataShape:
    def test_a_payload_with_neither_signals_nor_instruments_cites_nothing(self):
        assert sources.build(state_for("MARKET_DATA_AGENT", {"symbol": "THYAO"})) == []

    def test_signals_without_a_symbol_cites_nothing(self):
        assert sources.build(state_for("MARKET_DATA_AGENT", {"signals": {"observations": 5}})) == []

    def test_an_empty_instrument_list_cites_nothing(self):
        assert sources.build(state_for("MARKET_DATA_AGENT", {"instruments": []})) == []
