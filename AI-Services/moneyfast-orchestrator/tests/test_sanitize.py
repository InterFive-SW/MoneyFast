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


class TestRiskProfileIdentifiers:
    """The risk summary added a second enum family to leak.

    A source enum ("YFINANCE_DELAYED") names the plumbing behind a number the
    user can still read. An alignment enum IS the finding: strip it and the
    sentence loses its verb, so these get a Turkish meaning rather than a
    category noun.
    """

    def test_alignment_enums_become_the_thing_they_mean(self):
        out, found = sanitize.sanitize("Durumunuz: PORTFOLIO_RISKIER.")
        assert out == "Durumunuz: beyan ettiğiniz bandın üzerinde."
        assert found == ["PORTFOLIO_RISKIER"]

    def test_the_calm_side_is_not_left_as_an_enum(self):
        out, _ = sanitize.sanitize("Sonuç PORTFOLIO_CALMER çıktı.")
        assert "beyan ettiğiniz bandın altında" in out
        assert "PORTFOLIO_CALMER" not in out

    def test_agreement_reads_as_agreement(self):
        out, _ = sanitize.sanitize("Sonuç ALIGNED.")
        assert out == "Sonuç beyan ettiğiniz bandla aynı."

    def test_the_two_halves_of_the_comparison_are_never_named(self):
        """`measured_level` and `declared_tolerance` are the likeliest field
        names in this payload to be written out, because the reply is ABOUT
        the two things they name."""
        out, found = sanitize.sanitize(
            "measured_level Yüksek, declared_tolerance Orta."
        )
        assert "measured_level" not in out and "declared_tolerance" not in out
        assert set(found) == {"measured_level", "declared_tolerance"}
        assert "Yüksek" in out and "Orta" in out

    def test_the_turkish_band_labels_survive(self):
        """The bands are the answer. Only the keys around them go."""
        text = "Ölçülen seviyeniz Düşük, beyanınız Orta."
        assert sanitize.sanitize(text) == (text, [])

    def test_quality_keys_do_not_reach_the_user(self):
        out, found = sanitize.sanitize(
            "Ölçüm 249 gözlem üzerinden (is_statistically_reliable true)."
        )
        assert "is_statistically_reliable" not in out
        assert "249 gözlem" in out
        assert "is_statistically_reliable" in found


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


class TestDirectionInternals:
    """v2.21. `lean` bir SIRALAMA büyüklüğü ve kullanıcıya hiçbir şey
    söylemiyor. Ölçüldü: model onu "(lean -%0,017)" diye cevabın içine yazdı,
    araç sözleşmesi açıkça yasaklamasına rağmen -- prompt tavsiyedir."""

    def test_the_ordering_magnitude_is_removed(self):
        out, removed = sanitize.sanitize(
            "Veriler düşüşe işaret ediyor (lean -%0,017)."
        )
        assert "lean" not in out
        assert "lean" in removed

    def test_the_coverage_bookkeeping_is_removed(self):
        """Okumanın muhasebesi, okumanın kendisi değil."""
        out, removed = sanitize.sanitize(
            "sources_measured 3 ve evidence_count 13 olarak ölçüldü."
        )
        assert "sources_measured" not in out
        assert "evidence_count" not in out

    def test_an_ordinary_word_is_not_touched(self):
        """Temizleyici TANIMLAYICI arıyor, kelime değil: aksi hâlde sıradan
        Türkçe metni de keserdi."""
        text = "Şirketin borçlanma eğilimi arttı."
        out, removed = sanitize.sanitize(text)
        assert out == text
        assert removed == []
