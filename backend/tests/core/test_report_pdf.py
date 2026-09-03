"""Raporun PDF hâli.

Bu dosyanın koruduğu iki şey:

TÜRKÇE BOZULMAZ. `fpdf`'in gömülü çekirdek fontları latin-1 ve ı, ş, ğ
harflerini taşımıyor; mevcut KVKK dışa aktarımı bu yüzden "Kisisel",
"Olusturulma" diye yazmak zorunda kalmış. Rapor kullanıcıya gösterilen bir
belge ve aksanları düşürülmüş Türkçe, yanlış yazılmış Türkçedir. Font yoksa
PDF ÜRETİLMİYOR -- sessizce bozuk metin, hiç belge olmamasından kötü.

METİN ÜRETİLMEZ. Bölüm başlıkları ve cümleleri `analytics/report.py`'de bir
kez kuruluyor; PDF yalnızca onları sayfaya yerleştiriyor. Ekran, sohbet ve
PDF aynı metni okumalı.
"""

from __future__ import annotations

import io

import pypdf
import pytest

from app.core import pdf_generator

REPORT = {
    "generated_at": "2026-09-03T06:47:23Z",
    "as_of": "2026-09-02T14:35:14Z",
    "is_delayed": True,
    "delay_minutes": 987,
    "currency_code": "TRY",
    "sections": [
        {"key": "overview", "title": "Genel bakış",
         "summary": "Toplam varlığınız 24.405,27 TRY.",
         "lines": ["Nakit: 1.369,26 TRY", "Pozisyon sayısı: 8"], "rows": []},
        {"key": "drift", "title": "Hedef dağılımdan sapma",
         "summary": "En büyük fark BIST Hisse kovasında: hedefiniz %60, "
                    "ölçülen ağırlık %90,4 — hedefin 30,4 puan üzerinde.",
         "lines": [], "rows": []},
    ],
}


def text_of(content: bytes) -> str:
    """PDF'in metnini geri okur.

    `importorskip` DEĞİL: `pypdf` uygulamanın kendi bağımlılığı
    (requirements.txt), dolayısıyla atlanabilir bir test burada sessizce
    korumayı bırakan bir test olurdu.
    """
    reader = pypdf.PdfReader(io.BytesIO(content))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


class TestTurkish:
    def test_the_document_is_produced(self):
        content = pdf_generator.generate_report_pdf(REPORT)
        assert content.startswith(b"%PDF")

    @pytest.mark.parametrize(
        "word",
        ["Detaylı", "Oluşturulma", "varlığınız", "dağılımdan", "ağırlık",
         "Genel bakış", "büyük"],
    )
    def test_turkish_letters_survive(self, word):
        """ı, ş, ğ, ö, ü, ç -- gömülü fontların hiçbirinde yok."""
        assert word in text_of(pdf_generator.generate_report_pdf(REPORT))

    def test_the_em_dash_survives(self):
        assert "—" in text_of(pdf_generator.generate_report_pdf(REPORT))


class TestNoFont:
    def test_a_missing_font_refuses_rather_than_dropping_the_accents(
        self, monkeypatch
    ):
        """Aksanları düşürülmüş Türkçe yanlış yazılmış Türkçedir; sessizce
        bozuk bir belge vermektense hiç vermemek doğru."""
        monkeypatch.setattr(pdf_generator, "DEJAVU_REGULAR", "/yok/DejaVuSans.ttf")
        with pytest.raises(pdf_generator.UnicodeFontMissing):
            pdf_generator.generate_report_pdf(REPORT)

    def test_the_bold_face_is_required_too(self, monkeypatch):
        monkeypatch.setattr(pdf_generator, "DEJAVU_BOLD", "/yok/DejaVuSans-Bold.ttf")
        with pytest.raises(pdf_generator.UnicodeFontMissing):
            pdf_generator.generate_report_pdf(REPORT)


class TestContent:
    def test_every_section_reaches_the_page(self):
        page = text_of(pdf_generator.generate_report_pdf(REPORT))
        for section in REPORT["sections"]:
            assert section["title"] in page
            assert section["summary"].split(":")[0] in page

    def test_the_lines_reach_the_page(self):
        page = text_of(pdf_generator.generate_report_pdf(REPORT))
        assert "Pozisyon sayısı: 8" in page

    def test_the_price_time_is_stated_separately_from_the_build_time(self):
        """Raporu üretim saatiyle tarihlemek, fiyatları olduğundan taze
        göstermek olurdu."""
        page = text_of(pdf_generator.generate_report_pdf(REPORT))
        assert "987 dakika gecikmeli" in page
        assert REPORT["as_of"] in page and REPORT["generated_at"] in page

    def test_a_fresh_report_carries_no_delay_line(self):
        page = text_of(pdf_generator.generate_report_pdf(
            {**REPORT, "is_delayed": False}
        ))
        assert "gecikmeli" not in page

    def test_a_report_with_no_sections_is_still_a_document(self):
        """Boş bir rapor bozuk bir dosya değil: başlığı ve zaman damgası
        olan, bölümü olmayan bir belge."""
        content = pdf_generator.generate_report_pdf({**REPORT, "sections": []})
        assert content.startswith(b"%PDF")
        assert "Detaylı Rapor" in text_of(content)

    def test_a_section_without_a_summary_still_renders_its_lines(self):
        """Cümlesi olmayan bölüm atlanmıyor: satırları hâlâ raporun parçası."""
        page = text_of(pdf_generator.generate_report_pdf({
            **REPORT,
            "sections": [{"key": "x", "title": "Pozisyonlar", "summary": "",
                          "lines": ["DOAS: 100 adet"], "rows": []}],
        }))
        assert "Pozisyonlar" in page and "DOAS: 100 adet" in page

    def test_the_logo_is_optional(self, monkeypatch, tmp_path):
        """Logo dosyası yoksa belge yine üretiliyor: eksik bir görsel,
        raporun içeriğini engellememeli."""
        real_exists = pdf_generator.os.path.exists
        monkeypatch.setattr(
            pdf_generator.os.path, "exists",
            lambda path: False if path.endswith(".png") else real_exists(path),
        )
        assert pdf_generator.generate_report_pdf(REPORT).startswith(b"%PDF")

    def test_it_writes_bytes_rather_than_a_file(self):
        """Pozisyonları, bakiyeyi ve maaşı bir arada taşıyan bir belgenin
        geçici dizinde unutulması, temizlenmesi hatırlanması gereken bir şey
        olurdu."""
        assert isinstance(pdf_generator.generate_report_pdf(REPORT), bytes)
