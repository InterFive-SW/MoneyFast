"""Yüklenen dosyalardan metin çıkarımı.

Saf fonksiyonlar: girdi bayt, çıktı metin. Veritabanı yok, ağ yok --
`market/technicals.py` ile aynı gerekçe, elle kurulmuş girdilere karşı test
edilebilsin diye.

**Çıkarılan metin GÜVENİLMEZ.** `Markdown.tsx` ham HTML render etmiyor çünkü
"bir kısmı RAG ile getirilen belgelerden türer, yani güvenilmez girdidir".
Yüklenen dosya aynı sınıfın daha kötüsü: içeriğini tamamen kullanıcı
belirliyor. Buradan çıkan metin modele TALİMAT olarak değil VERİ olarak
verilir ve çağıran onu enjeksiyon taramasından geçirir.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from typing import Callable, Optional

log = logging.getLogger(__name__)

#: Kabul edilen biçimler: uzantı -> okunabilir ad.
#:
#: Uzantıya göre, MIME'a göre DEĞİL: tarayıcılar aynı dosya için farklı MIME
#: gönderiyor (bir .csv "text/csv", "application/vnd.ms-excel" ya da boş
#: gelebiliyor) ve MIME'a güvenmek, kullanıcının yüklediği dosyanın
#: reddedilmesi demekti.
SUPPORTED = {
    ".pdf": "PDF",
    ".xlsx": "Excel",
    ".xls": "Excel",
    ".csv": "CSV",
    ".pptx": "PowerPoint",
    ".txt": "Metin",
}

#: Yükleme boyutu tavanı. 10 MB, bir bilanço PDF'i için fazlasıyla yeterli.
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

#: Çıkarılan metin tavanı. Ayrı bir sınır, çünkü küçük bir dosya çok metin
#: üretebilir: 2 MB'lık bir XLSX yüz binlerce hücre demek olabilir.
MAX_TEXT_CHARS = 400_000

#: Elektronik tablodan en fazla kaç satır okunur. Bunun ötesi bir belge
#: değil bir veri kümesidir ve gömme için parçalanması anlamlı olmaz.
MAX_SHEET_ROWS = 5_000


class UnsupportedDocument(Exception):
    """Biçim desteklenmiyor."""


class UnreadableDocument(Exception):
    """Biçim doğru ama dosya okunamadı: bozuk, şifreli ya da boş."""


@dataclass(frozen=True)
class Extracted:
    """Bir dosyadan çıkan her şey."""

    text: str
    #: PDF'te sayfa, tabloda satır, sunumda slayt. Kullanıcıya "neyin
    #: okunduğunu" söyleyen sayı.
    units: int
    #: `MAX_TEXT_CHARS`'a takıldı mı. Sessizce kırpmak, belgenin yarısını
    #: okuyup tamamını okumuş gibi cevap vermek olurdu.
    truncated: bool


def extension_of(filename: str) -> str:
    """Dosya adının küçük harfli uzantısı, noktası dahil."""
    _, dot, suffix = (filename or "").rpartition(".")
    return f".{suffix.lower()}" if dot else ""


def extract(filename: str, payload: bytes) -> Extracted:
    """Dosyayı metne çevirir.

    Bilinmeyen uzantı `UnsupportedDocument`, okunamayan içerik
    `UnreadableDocument` fırlatır. İkisi ayrı, çünkü kullanıcının yapacağı
    şey farklı: biri "bu biçimi desteklemiyoruz", diğeri "bu dosya bozuk".
    """
    extension = extension_of(filename)
    reader = _READERS.get(extension)
    if reader is None:
        raise UnsupportedDocument(extension or filename)
    if not payload:
        raise UnreadableDocument("dosya boş")

    try:
        text, units = reader(payload)
    except (UnsupportedDocument, UnreadableDocument):
        raise
    except Exception as exc:  # sağlayıcı kütüphanelerin hata sınıfları çeşitli
        log.warning("document extraction failed for %s: %s", filename, exc)
        raise UnreadableDocument(str(exc)) from exc

    text = text.strip()
    if not text:
        # Taranmış bir PDF görüntüdür ve içinde metin yoktur. "Yüklendi"
        # deyip aramada hiç çıkmaması, sessizce başarısız olmaktır.
        raise UnreadableDocument("dosyadan metin çıkarılamadı")

    truncated = len(text) > MAX_TEXT_CHARS
    return Extracted(text=text[:MAX_TEXT_CHARS], units=units, truncated=truncated)


def _read_txt(payload: bytes) -> tuple[str, int]:
    """Metni çöz. Bu fonksiyonun başarısızlık yolu YOKTUR.

    Sırayla utf-8 ve cp1254 deneniyor (Türkçe metin hâlâ ikincisiyle de
    dolaşıyor; değiştirerek çözmek ı/ş/ğ'yi soru işaretine çevirirdi).
    Son çare latin-1 HER bayt dizisini kabul eder, dolayısıyla buradan
    çıkılamayan bir dal olmuyor -- ve olmayan bir dal için hata yolu
    yazmak, hiçbir şeyin doğrulamadığı bir davranış iddiası olurdu.

    Anlamsız metin çıkarsa onu yakalayan yer `extract`: metin boşsa ya da
    yalnızca boşluksa belge okunamamış sayılıyor.
    """
    for encoding in ("utf-8", "cp1254"):
        try:
            text = payload.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = payload.decode("latin-1")
    return text, text.count("\n") + 1


def _read_csv(payload: bytes) -> tuple[str, int]:
    text, _ = _read_txt(payload)
    rows = list(csv.reader(io.StringIO(text)))[:MAX_SHEET_ROWS]
    # Satırlar boru işaretiyle birleştiriliyor: gömme modeli virgülden çok
    # bir tablo satırı gibi okur ve sütun sınırları korunur.
    lines = [" | ".join(cell.strip() for cell in row) for row in rows if any(row)]
    return "\n".join(lines), len(lines)


def _read_pdf(payload: bytes) -> tuple[str, int]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(payload))
    if reader.is_encrypted:
        # Boş parola ile açılabilenler var; açılamıyorsa bu bir hata değil,
        # kullanıcının bilmesi gereken bir durum.
        try:
            reader.decrypt("")
        except Exception as exc:
            raise UnreadableDocument("PDF şifreli") from exc

    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages), len(pages)


def _read_xlsx(payload: bytes) -> tuple[str, int]:
    from openpyxl import load_workbook

    # `data_only`: formül metni değil, hesaplanmış değer. "=B2*1,2" bir
    # olgu değildir; 4.812 olgudur.
    book = load_workbook(io.BytesIO(payload), read_only=True, data_only=True)
    lines: list[str] = []
    try:
        for sheet in book.worksheets:
            lines.append(f"# {sheet.title}")
            for row in sheet.iter_rows(values_only=True):
                if len(lines) >= MAX_SHEET_ROWS:
                    break
                cells = [str(c).strip() for c in row if c is not None]
                if cells:
                    lines.append(" | ".join(cells))
    finally:
        book.close()
    return "\n".join(lines), len(lines)


def _read_pptx(payload: bytes) -> tuple[str, int]:
    from pptx import Presentation

    deck = Presentation(io.BytesIO(payload))
    slides: list[str] = []
    for index, slide in enumerate(deck.slides, start=1):
        pieces = [
            shape.text.strip()
            for shape in slide.shapes
            if getattr(shape, "has_text_frame", False) and shape.text.strip()
        ]
        if pieces:
            slides.append(f"# Slayt {index}\n" + "\n".join(pieces))
    return "\n\n".join(slides), len(deck.slides)


def _read_xls(payload: bytes) -> tuple[str, int]:
    """`.xls` uzantılı dosya.

    Uzantı biçimi GARANTİ ETMEZ: dışa aktarma yapan çok sayıda araç bir xlsx
    (hatta bir CSV) üretip ona .xls adını veriyor. O yüzden önce gerçekten ne
    olduğuna bakılıyor -- ZIP başlığı (`PK`) bir xlsx'tir.

    Gerçekten eski ikili biçimse okunmuyor: `openpyxl` onu desteklemiyor ve
    `xlrd` 2.0 ile desteği kaldırdı; kalan seçenek bakımsız bir sürümü
    sabitlemek olurdu. Kullanıcıya ne yapacağını söylemek, bunu yapmaktan da
    sessizce boş bir belge yazmaktan da iyi.
    """
    if payload[:2] == b"PK":
        return _read_xlsx(payload)
    # Eski ikili Excel'in kendi imzası. Tanımak, hata mesajını tahmin
    # olmaktan çıkarıyor.
    if payload[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        raise UnsupportedDocument(
            "eski Excel biçimi (.xls) okunamıyor; dosyayı .xlsx olarak "
            "kaydedip yeniden yükleyin"
        )
    # .xls adı taşıyan ama ikisi de olmayan bir dosya: çoğunlukla CSV ya da
    # HTML tablo. Metin olarak denemek, reddetmekten iyi.
    return _read_csv(payload)


_READERS: dict[str, Callable[[bytes], tuple[str, int]]] = {
    ".txt": _read_txt,
    ".csv": _read_csv,
    ".pdf": _read_pdf,
    ".xlsx": _read_xlsx,
    ".xls": _read_xls,
    ".pptx": _read_pptx,
}
