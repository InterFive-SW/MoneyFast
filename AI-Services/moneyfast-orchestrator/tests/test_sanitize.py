"""Keeping internal identifiers out of what the user reads.

Every input below is a real string from `ai.messages`, or a near neighbour of
one. The point of these tests is not that the token disappears — that is easy —
but that the sentence still reads as Turkish afterwards, and that ordinary
text with numbers in it is left completely alone.
"""

from __future__ import annotations

import pytest

import sanitize


class TestSourceEnums:
    def test_the_provider_enum_becomes_a_turkish_word(self):
        out, found = sanitize.sanitize(
            "Veri YFINANCE_DELAYED kaynağından, 17 dk gecikmeli."
        )
        assert out == "Veri sağlayıcı kaynağından, 17 dk gecikmeli."
        assert "YFINANCE_DELAYED" in found

    def test_the_analytics_enum_too(self):
        out, _ = sanitize.sanitize("Kaynak: MONEYFAST_FIXTURE_ANALYTICS, 252 gözlem.")
        assert out == "Kaynak: dahili analiz, 252 gözlem."

    def test_the_replacement_does_not_repeat_the_delay_word(self):
        """"gecikmeli piyasa verisi ... gecikmeli" reads badly; the observed
        sentence already carries the delay."""
        out, _ = sanitize.sanitize("Veri YFINANCE_DELAYED kaynağından, 17 dk gecikmeli.")
        assert out.count("gecikmeli") == 1


class TestParentheticals:
    def test_a_timestamp_parenthetical_is_removed_whole(self):
        """Removing only the token would leave "( 2026-08-21 13:32)"."""
        out, found = sanitize.sanitize(
            "17 dk gecikmeli (as_of 2026-08-21 13:32)."
        )
        assert out == "17 dk gecikmeli."
        assert "as_of" in found

    def test_a_bare_key_parenthetical_is_removed(self):
        out, _ = sanitize.sanitize(
            "sıralama = günlük yüzde değişim (change_percent) yüksekten düşüğe"
        )
        assert out == "sıralama = günlük yüzde değişim yüksekten düşüğe"

    def test_a_normal_parenthetical_survives(self):
        text = "Komisyon (BSMV dahil) 6,04 TL."
        assert sanitize.sanitize(text) == (text, [])


class TestBareIdentifiers:
    @pytest.mark.parametrize(
        "key", ["max_weight", "order_type", "price_history", "market_corpus", "user_id"]
    )
    def test_each_observed_key_is_removed(self, key):
        out, found = sanitize.sanitize(f"Değer {key} olarak alındı.")
        assert key not in out
        assert key in found

    def test_a_key_inside_a_longer_word_is_left_alone(self):
        """Substring matching would corrupt ordinary text."""
        text = "as_office kelimesi bir alan adı değil."
        assert sanitize.sanitize(text) == (text, [])


class TestLeavesRealAnswersAlone:
    @pytest.mark.parametrize("text", [
        "THYAO 302,25 TL, günlük hacim 27.813.771 adet.",
        "Fiyatlar 15 dakika gecikmeli; 21 Ağustos 13:32 itibarıyla.",
        "**Yatırım tavsiyesi olarak değil, objektif kriterlerle taradım.**",
        "| Hisse | Sektör | Fiyat | F/K |",
        "",
    ])
    def test_untouched(self, text):
        assert sanitize.sanitize(text) == (text, [])

    def test_figures_are_never_edited(self):
        out, _ = sanitize.sanitize("Bakiye 39.010,69 TL (as_of 2026-08-21).")
        assert "39.010,69 TL" in out


class TestSanitizedWrapper:
    def test_reports_what_it_removed(self, caplog):
        with caplog.at_level("WARNING"):
            sanitize.sanitized("Veri YFINANCE_DELAYED kaynağından.", trace_id="abc123")
        assert "YFINANCE_DELAYED" in caplog.text
        assert "abc123" in caplog.text

    def test_says_nothing_when_the_text_is_already_clean(self, caplog):
        with caplog.at_level("WARNING"):
            sanitize.sanitized("THYAO 302,25 TL.")
        assert caplog.text == ""

    def test_a_cleaner_failure_never_costs_the_turn(self, mocker, caplog):
        """The reply matters more than the cleaning."""
        mocker.patch.object(sanitize, "sanitize", side_effect=RuntimeError("boom"))
        with caplog.at_level("WARNING"):
            assert sanitize.sanitized("orijinal metin") == "orijinal metin"
        assert "sanitize failed" in caplog.text
