"""Yüklenen dosyalardan metin çıkarımı.

Çıkarılan metin GÜVENİLMEZ: içeriğini tamamen kullanıcı belirliyor. Buradaki
testler ne çıkarıldığını sabitliyor; içeriğin nasıl çerçevelendiği çağıranın
işi.
"""

import io
import zipfile

import pytest

from app.modules.ai_orchestrator import documents


class TestExtensions:
    def test_it_reads_the_extension_case_insensitively(self):
        assert documents.extension_of("Bilanço.PDF") == ".pdf"
        assert documents.extension_of("a.b.CSV") == ".csv"

    def test_a_file_without_one_has_none(self):
        assert documents.extension_of("LICENSE") == ""
        assert documents.extension_of("") == ""

    def test_the_five_named_formats_are_accepted(self):
        for extension in (".pdf", ".xlsx", ".xls", ".csv", ".pptx", ".txt"):
            assert extension in documents.SUPPORTED


class TestPlainText:
    def test_utf8_survives_turkish(self):
        out = documents.extract("a.txt", "Hasılat 585 milyar TL.".encode("utf-8"))
        assert "Hasılat" in out.text

    def test_a_windows_turkish_encoding_is_tried_before_giving_up(self):
        """cp1254 dosyaları hâlâ dolaşımda. utf-8 başarısız olduğunda
        değiştirerek çözmek ı/ş/ğ'yi soru işaretine çevirirdi."""
        out = documents.extract("a.txt", "Hasılat şirketi".encode("cp1254"))
        assert "ş" in out.text

    def test_line_count_is_reported(self):
        out = documents.extract("a.txt", b"bir\niki\nuc")
        assert out.units == 3


class TestCsv:
    def test_rows_become_pipe_separated_lines(self):
        """Boru işareti, gömme modeline bir tablo satırı gibi okunur ve
        sütun sınırları korunur."""
        out = documents.extract("a.csv", b"sembol,fiyat\nTHYAO,304")
        assert "sembol | fiyat" in out.text
        assert "THYAO | 304" in out.text

    def test_blank_rows_are_dropped(self):
        out = documents.extract("a.csv", b"a,b\n\n\nc,d")
        assert out.units == 2


class TestXls:
    """`.xls` bir uzantıdır, bir biçim garantisi değil."""

    def test_an_xlsx_wearing_an_xls_name_is_read(self):
        """Dışa aktarma yapan çok sayıda araç xlsx üretip .xls adını
        veriyor."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types/>")
        payload = buffer.getvalue()
        assert payload[:2] == b"PK"
        # openpyxl bunu geçerli bir çalışma kitabı bulamayacak, ama yol
        # xlsx okuyucusuna gitmeli -- "eski biçim" hatası ALMAMALI.
        with pytest.raises(documents.UnreadableDocument):
            documents.extract("a.xls", payload)

    def test_the_genuine_legacy_format_says_what_to_do_about_it(self):
        payload = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 32
        with pytest.raises(documents.UnsupportedDocument) as exc:
            documents.extract("a.xls", payload)
        assert ".xlsx" in str(exc.value)

    def test_an_xls_that_is_really_a_csv_is_read_as_one(self):
        out = documents.extract("a.xls", b"sembol,fiyat\nTHYAO,304")
        assert "THYAO | 304" in out.text


class TestRefusals:
    def test_an_unknown_format_is_refused_by_name(self):
        with pytest.raises(documents.UnsupportedDocument):
            documents.extract("a.docx", b"anything")

    def test_an_empty_file_is_unreadable_not_unsupported(self):
        """İki ayrı durum: biri "bu biçimi desteklemiyoruz", diğeri "bu dosya
        bozuk". Kullanıcının yapacağı şey farklı."""
        with pytest.raises(documents.UnreadableDocument):
            documents.extract("a.txt", b"")

    def test_a_file_with_no_extractable_text_is_refused(self):
        """Taranmış bir PDF bir görüntüdür. "Yüklendi" deyip aramada hiç
        çıkmaması, sessizce başarısız olmaktır."""
        with pytest.raises(documents.UnreadableDocument):
            documents.extract("a.txt", b"   \n\t  ")

    def test_a_corrupt_file_raises_unreadable_rather_than_propagating(self):
        with pytest.raises(documents.UnreadableDocument):
            documents.extract("a.pdf", b"this is not a pdf")

    def test_bytes_neither_encoding_accepts_fall_back_to_latin1(self):
        """0x81 cp1254'te tanımsız ve 0xFF geçerli bir utf-8 başlangıcı
        değil. latin-1 her bayt dizisini kabul eder, dolayısıyla metin okuma
        yolunun başarısızlık dalı YOKTUR -- ve olmayan bir dal için hata
        yolu yazmak, hiçbir şeyin doğrulamadığı bir davranış iddiası
        olurdu."""
        out = documents.extract("a.txt", bytes([0xFF, 0x81]) + b" THYAO")
        assert "THYAO" in out.text

    def test_bytes_no_encoding_claims_still_produce_something(self):
        """latin-1 her bayt dizisini kabul eder, dolayısıyla metin okuma
        yolunun başarısızlık dalı yoktur. Anlamsız çıktıyı yakalayan yer
        `extract`'in boş metin denetimi."""
        out = documents.extract("a.txt", b"\xff\xfe THYAO \x00")
        assert "THYAO" in out.text


class TestTruncation:
    def test_a_long_document_is_cut_and_says_so(self, monkeypatch):
        """Sessizce kırpmak, belgenin yarısını okuyup tamamını okumuş gibi
        cevap vermek olurdu."""
        monkeypatch.setattr(documents, "MAX_TEXT_CHARS", 20)
        out = documents.extract("a.txt", ("x" * 100).encode())

        assert out.truncated is True
        assert len(out.text) == 20

    def test_a_short_document_is_not_marked_truncated(self):
        assert documents.extract("a.txt", b"kisa").truncated is False


# ---------------------------------------------------------------------------
# Gerçek dosyalar
# ---------------------------------------------------------------------------
#
# Bu testler dosyaları ÜRETİP okuyor, sahte bayt dizileri değil. Bir PDF
# okuyucusunun gerçekten PDF okuduğunu, taklit edilmiş bir kütüphane
# gösteremez.


def _pdf(pages: list[str]) -> bytes:
    from fpdf import FPDF

    pdf = FPDF()
    for text in pages:
        pdf.add_page()
        pdf.set_font("helvetica", size=12)
        pdf.cell(0, 10, text)
    return bytes(pdf.output())


def _xlsx(rows: list[list]) -> bytes:
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.title = "Bilanco"
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _pptx(slides: list[str]) -> bytes:
    from pptx import Presentation

    deck = Presentation()
    for text in slides:
        slide = deck.slides.add_slide(deck.slide_layouts[5])
        slide.shapes.title.text = text
    buffer = io.BytesIO()
    deck.save(buffer)
    return buffer.getvalue()


class TestPdf:
    def test_text_and_page_count_come_out(self):
        out = documents.extract("a.pdf", _pdf(["Hasilat 585 milyar TL", "Marj 9,8"]))
        assert "585" in out.text
        assert out.units == 2

    def test_pages_are_separated(self):
        out = documents.extract("a.pdf", _pdf(["birinci", "ikinci"]))
        assert "birinci" in out.text and "ikinci" in out.text


class TestXlsx:
    def test_cells_become_pipe_separated_rows(self):
        out = documents.extract("a.xlsx", _xlsx([["sembol", "fiyat"], ["THYAO", 304]]))
        assert "sembol | fiyat" in out.text
        assert "THYAO | 304" in out.text

    def test_the_sheet_name_is_kept(self):
        """Bir çalışma kitabında hangi sayfadan geldiği bilginin parçası."""
        out = documents.extract("a.xlsx", _xlsx([["a"]]))
        assert "# Bilanco" in out.text

    def test_empty_cells_do_not_produce_empty_columns(self):
        out = documents.extract("a.xlsx", _xlsx([["a", None, "b"]]))
        assert "a | b" in out.text

    def test_a_row_cap_keeps_a_dataset_from_becoming_a_document(self, monkeypatch):
        monkeypatch.setattr(documents, "MAX_SHEET_ROWS", 3)
        out = documents.extract("a.xlsx", _xlsx([[i] for i in range(50)]))
        assert len(out.text.splitlines()) <= 3

    def test_a_sheet_that_ends_in_blank_rows_finishes_normally(self):
        """Kapasiteye takılmadan biten döngü: son satırlar boş olduğu için
        hiçbir şey eklenmiyor ve döngü kendi sonuna varıyor."""
        out = documents.extract(
            "a.xlsx", _xlsx([["THYAO", 304], [None, None], [None, None]])
        )
        assert "THYAO | 304" in out.text
        assert out.text.count("|") == 1


class TestPptx:
    def test_slide_text_and_count_come_out(self):
        out = documents.extract("a.pptx", _pptx(["Ceyrek sonuclari", "Gorunum"]))
        assert "Ceyrek sonuclari" in out.text
        assert out.units == 2

    def test_slides_are_numbered(self):
        out = documents.extract("a.pptx", _pptx(["baslik"]))
        assert "# Slayt 1" in out.text

    def test_a_deck_with_no_text_at_all_is_unreadable(self):
        """Yalnızca görsel içeren bir sunumdan metin çıkmaz; "yüklendi" deyip
        aramada hiç çıkmaması sessizce başarısız olmaktır."""
        from pptx import Presentation

        deck = Presentation()
        deck.slides.add_slide(deck.slide_layouts[6])  # boş düzen
        buffer = io.BytesIO()
        deck.save(buffer)

        with pytest.raises(documents.UnreadableDocument):
            documents.extract("a.pptx", buffer.getvalue())


class TestEncryptedPdf:
    def test_an_encrypted_pdf_says_so(self, mocker):
        reader = mocker.patch("pypdf.PdfReader")
        reader.return_value.is_encrypted = True
        reader.return_value.decrypt.side_effect = RuntimeError("no password")

        with pytest.raises(documents.UnreadableDocument):
            documents.extract("a.pdf", b"%PDF-1.4 fake")

    def test_an_empty_password_is_tried_first(self, mocker):
        """Şifreli işaretli ama boş parolayla açılan PDF'ler yaygın."""
        reader = mocker.patch("pypdf.PdfReader")
        reader.return_value.is_encrypted = True
        reader.return_value.decrypt.return_value = 1
        page = mocker.Mock()
        page.extract_text.return_value = "Hasilat 585"
        reader.return_value.pages = [page]

        out = documents.extract("a.pdf", b"%PDF-1.4 fake")

        assert "585" in out.text
