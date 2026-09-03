"""Haber metnini enstrüman evrenindeki sembollere bağlar.

Saf fonksiyonlar: evren dışarıdan verilir, veritabanı bilgisi yok. Böylece
eşleştirme elle kontrol edilmiş girdilere karşı test edilebiliyor -- ki bu
modülde en çok ihtiyaç duyulan şey o, çünkü buradaki her hata bir şirketin
haberini başka bir şirketin sayfasına koyar.

**Kaçırmak, yanlış bağlamaktan iyidir.** Eşleşmeyen bir haber yalnızca
listede görünmez; yanlış eşleşen bir haber kullanıcıya sahip olmadığı bir
şirket hakkında bilgi veriyormuş gibi görünür ve fark edilmesi çok daha zor.
Bu yüzden burada bulanık eşleşme, kısmi ad eşleşmesi ve tahmin YOK.
"""

from __future__ import annotations

import html
import re
from typing import Any, Iterable, Optional

#: Türkçe harfleri ASCII'ye katlar. Amaç güzel görünmek değil, aynı ismin
#: farklı yazımlarını (İ/I/ı, büyük/küçük harf, eksik şapka) tek biçime
#: indirmek: "TÜPRAŞ", "Tüpraş" ve "TUPRAS" aynı şirkettir.
_FOLD = str.maketrans({
    "İ": "i", "I": "i", "ı": "i", "Ş": "s", "ş": "s", "Ğ": "g", "ğ": "g",
    "Ü": "u", "ü": "u", "Ö": "o", "ö": "o", "Ç": "c", "ç": "c", "Â": "a",
    "â": "a", "Î": "i", "î": "i", "Û": "u", "û": "u",
})

#: Ticari unvan sonekleri. Haber başlıkları bunları yazmaz ("Türk Hava
#: Yolları'ndan rekor"), resmî unvan ise her zaman taşır.
#:
#: `holding` BURAYA GİRMEZ: şirketin adının parçasıdır, hukuki biçimi değil.
#: Sonek sayıldığında "KOÇ HOLDİNG A.Ş." çekirdeği "koc"a iniyordu -- üç harf,
#: hiçbir yoldan eşleşmez, dolayısıyla Koç Holding haberleri hep kaçıyordu.
#: "koc holding" ise hem eşleşir hem de "koç burcu" gibi sıradan metne
#: bulaşmaz.
_LEGAL_SUFFIX = re.compile(r"\s*(?:t\.?a\.?[soş]\.?|a\.?[soş]\.?|a\.?o\.?)\s*$")

#: Kesme işareti Türkçede özel adlara gelen eki ayırır: "Aselsan'ın".
#: Boşluğa çevrilince çekirdek ad yine bir alt dize olarak bulunabilir.
_APOSTROPHE = re.compile(r"['’`´]")

_NON_WORD = re.compile(r"[^a-z0-9]+")

#: HTML etiketleri ve öznitelikleri. RSS özetleri işaretlemeyi olduğu gibi
#: taşıyor -- ölçülen örnek: `<img align="right" ... style="border: navy 1px
#: solid;" />`. Temizlenmeden eşleştirildiğinde `align` özniteliği Align
#: Technology'ye (ALGN) bağlanıyor ve 1.540 haberin 563'ü, konusuyla hiç
#: ilgisi olmayan bir NASDAQ şirketine iliştiriliyordu.
_HTML_TAG = re.compile(r"<[^>]*>")

#: Ticker eşleşmesinin alt sınırı. Üç harfli bir kod ("ODA", "TAV") sıradan
#: metinde tesadüfen geçebilir; dört harf BIST kodlarının da normu.
MIN_TICKER_LENGTH = 4

#: Tek kelimelik bir adın eşleşebilmesi için en az bu kadar harf. "logo",
#: "mavi" gibi dört harfli adlar sıradan metinde geçer.
MIN_NAME_LENGTH = 5

#: NEDEN KISA AD (ALIAS) YOK
#:
#: Denendi ve ölçüldü. "Turkcell" ya da "Aselsan" gibi tek kelimelik ticari
#: adlarla eşleştirmek, 1.540 haberde yakalamayı 54'ten 167'ye çıkarıyor --
#: ama getirdiklerinin önemli kısmı yanlış, çünkü bu adların çoğu aynı
#: zamanda sıradan kelime:
#:
#:     ZOREN  <- "Haakon'un ZORLU sınavı"        (zorlu = sıfat)
#:     EKGYO  <- "EMLAK vergisi düzenlemesi"     (emlak = sıradan ad)
#:     GESAN  <- "GİRİŞİM sermayesi fonları"     (girişim = teşebbüs)
#:     IZMDC  <- "İZMİR'de kongre"               (izmir = şehir)
#:     SWK    <- "Morgan STANLEY tahmini"        (başka bir şirket)
#:
#: Korpus frekansı ayırt etmiyor: `turkcell` 16 haberde geçiyor, `izmir` 13.
#: Büyük harf şartı da kurtarmıyor -- şehir ve soyadları da büyük harfle
#: yazılır. Evren 1.009 hisseye çıktığı için çakışma yüzeyi ayrıca büyük.
#:
#: Çözüm ELLE YAZILMIŞ bir liste ve aşağıda duruyor.


#: Ticari kısa adlar: haberin yazdığı ad -> sembol.
#:
#: 3 Eylül 2026'da elle yazıldı. Otomatik türetme DENENDİ VE ÖLÇÜLDÜ:
#: resmî unvanın ilk kelimesini kısa ad saymak korpusta felaket üretiyor --
#: `turkiye` 551 haberde geçiyor ve sekiz bankaya bağlanırdı, `izmir` 21,
#: `bursa` 19, `altin` 112, `zorlu` 8, `girisim` 12. Yüksek frekanslı
#: tokenların neredeyse tamamı sıradan Türkçe kelime (`kredi`, `satis`,
#: `konut`, `gunes`, `deniz`, `icecek`, `otomobil`). Frekans ayırt etmiyor.
#:
#: Bu yüzden liste ELLE ve şu kurala göre yazıldı: **bir kısa ad, ancak
#: yalnızca o şirketi gösteriyorsa buraya girer.** "zorlu" giremez (sıfat),
#: "zorlu enerji" girer. "emlak" giremez (sıradan ad), "emlak konut" girer.
#: "altin" giremez, "koza altin" girer. "garanti" giremez (teminat anlamı),
#: "garanti bbva" girer.
#:
#: BIST ve Nasdaq üyelik listeleriyle aynı disiplin (bkz. migration 0006,
#: 0010): elle yazılmış, tarihli, diff'te okunabilir. Bir şirket adını
#: değiştirdiğinde burası da değişir ve bu, sessizce bozulmaktan iyidir.
#:
#: Resmî unvanın çekirdeğiyle zaten eşleşen adlar BURAYA YAZILMAZ: "türk
#: hava yolları" ve "tüpraş" NAME yoluyla bulunuyor. Buradakiler haberin
#: kullandığı ama unvanda geçmeyen adlar.
ALIASES: dict[str, tuple[str, ...]] = {
    # Bankalar ve finans
    "AKBNK": ("akbank",),
    # "garanti bbva" BİLEREK YOK: "GARANTİ BBVA OPERASYONEL KİRALAMA" ayrı
    # bir şirket ve kısa ad onun haberini bankaya bağlıyordu. Ölçüldü, on iki
    # eşleşmenin bedeli budur -- ve bu modülün kuralı kaçırmayı yanlış
    # bağlamaya tercih ediyor.
    "GARAN": ("garanti bankasi",),
    "ISCTR": ("is bankasi", "isbank"),
    "YKBNK": ("yapi kredi",),
    "HALKB": ("halkbank",),
    "VAKBN": ("vakifbank",),
    "ALBRK": ("albaraka",),
    "SKBNK": ("sekerbank",),
    "TSKB": ("tskb",),
    "ISMEN": ("is yatirim",),
    # Havacılık ve ulaştırma
    "THYAO": ("thy",),
    "PGSUS": ("pegasus",),
    "TAVHL": ("tav havalimanlari",),
    "CLEBI": ("celebi hava",),
    # Sanayi ve savunma
    "ASELS": ("aselsan",),
    "OTKAR": ("otokar",),
    "TTRAK": ("turk traktor",),
    "FROTO": ("ford otosan",),
    "TOASO": ("tofas",),
    "KARSN": ("karsan",),
    "ARCLK": ("arcelik",),
    "VESTL": ("vestel",),
    "EREGL": ("erdemir",),
    "KRDMD": ("kardemir",),
    "BRSAN": ("borusan",),
    "CIMSA": ("cimsa",),
    "OYAKC": ("oyak cimento",),
    "SISE": ("sisecam",),
    "PETKM": ("petkim",),
    "GUBRF": ("gubretas",),
    "HEKTS": ("hektas",),
    "ALARK": ("alarko",),
    "TKFEN": ("tekfen",),
    "ENKAI": ("enka insaat",),
    # Perakende ve tüketim
    "BIMAS": ("bim magazalari",),
    "MGROS": ("migros",),
    "SOKM": ("sok marketler",),
    "ULKER": ("ulker",),
    "CCOLA": ("coca cola icecek",),
    "AEFES": ("anadolu efes",),
    "CRFSA": ("carrefoursa",),
    "VAKKO": ("vakko",),
    # Enerji ve holding
    "ZOREN": ("zorlu enerji",),
    "AKSEN": ("aksa enerji",),
    "ODAS": ("odas enerji",),
    "SMRTG": ("smart gunes",),
    "KCHOL": ("koc holding",),
    "SAHOL": ("sabanci holding",),
    "DOHOL": ("dogan holding",),
    "AGHOL": ("anadolu grubu",),
    "DOAS": ("dogus otomotiv",),
    # Gayrimenkul ve altın
    "EKGYO": ("emlak konut",),
    "KOZAL": ("koza altin",),
    "KOZAA": ("koza anadolu",),
    # Teknoloji ve iletişim
    "TCELL": ("turkcell",),
    "TTKOM": ("turk telekom",),
    "LOGO": ("logo yazilim",),
    "NETAS": ("netas",),
    "ARENA": ("arena bilgisayar",),
    # ABD -- Türkçe haberde bu şirketler ADIYLA anılıyor, koduyla değil
    "AAPL": ("apple",),
    "MSFT": ("microsoft",),
    "NVDA": ("nvidia",),
    "GOOGL": ("google", "alphabet"),
    "AMZN": ("amazon",),
    "TSLA": ("tesla",),
    "META": ("meta platforms",),
    "JPM": ("jpmorgan",),
}

#: Sembolden kısa adlara değil, kısa addan sembole: eşleştirme metinde ad
#: arıyor. Çakışan bir kısa ad (iki şirkete birden yazılmış) burada sessizce
#: birini eziyordu; bu yüzden kurulum sırasında hata veriyor.
def _build_alias_index() -> dict[str, str]:
    index: dict[str, str] = {}
    for symbol, names in ALIASES.items():
        for name in names:
            folded = _NON_WORD.sub(" ", name.translate(_FOLD).lower()).strip()
            if folded in index and index[folded] != symbol:
                raise ValueError(
                    f"kısa ad iki sembole birden yazılmış: {folded!r} -> "
                    f"{index[folded]}, {symbol}"
                )
            index[folded] = symbol
    return index


def strip_markup(text: str) -> str:
    """HTML etiketlerini atar, varlıkları çözer.

    Haber özetleri beslemeden işaretlemeyle geliyor. Etiketin İÇİ değil
    KENDİSİ atılıyor: `<img align="right" src="...">` tamamen gider, çünkü
    öznitelik adları ve URL'ler haberin metni değildir.

    Varlıklar SİLİNMİYOR, çözülüyor: "Türkiye&#039;nin" -> "Türkiye'nin".
    Silinseydi "Türkiye nin" kalırdı ve bu metin yalnızca eşleştirmeye değil
    ekrana da gidiyor. İki geçiş, çünkü beslemeler çift kaçışlı gönderiyor
    (`LPG&amp;#039;nin`); kararlı hâle gelince duruyor.

    `ingestor/sources/rss_source.py:clean_summary` ile aynı davranış. Kopya,
    çünkü iki ayrı servis ve aralarında paylaşılan kod yok. Kaynak orada
    temizlendiği için buradaki asıl işlev arşiv: düzeltmeden önce toplanmış
    1.548 haberin 922'si hâlâ işaretleme taşıyor.
    """
    text = _HTML_TAG.sub(" ", text or "")
    for _ in range(2):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped
    return re.sub(r"\s+", " ", text).strip()


def fold(text: str) -> str:
    """Türkçe metni eşleştirilebilir tek biçime indirger."""
    folded = _APOSTROPHE.sub(" ", strip_markup(text)).translate(_FOLD).lower()
    return _NON_WORD.sub(" ", folded).strip()


def core_name(name: str) -> str:
    """Resmî unvandan ticari unvan sonekini atar.

    "TÜRK HAVA YOLLARI A.O." -> "turk hava yollari". Sonek atılmadan
    eşleşme hiç tutmaz: hiçbir haber başlığı "A.O." yazmaz.
    """
    folded = _APOSTROPHE.sub(" ", name or "").translate(_FOLD).lower()
    folded = _NON_WORD.sub(" ", _LEGAL_SUFFIX.sub("", folded)).strip()
    # Sonek iki kez geçebilir ("... SANAYİ A.Ş. T.A.Ş." gibi bozuk kayıtlar).
    return _LEGAL_SUFFIX.sub("", folded).strip()


def _ticker_tokens(text: str) -> set[str]:
    """Metinde BÜYÜK HARFLE, tek başına geçen kelimeler.

    Büyük harf şartı kasıtlı: "SASA" bir şirket kodudur ama küçük harfle
    sıradan bir metinde geçebilir. Orijinal metin okunur, katlanmış hâli
    değil -- katlama büyük/küçük ayrımını yok eder.
    """
    return {token for token in re.findall(r"\b[A-ZÇĞİÖŞÜ0-9]{2,8}\b", text or "")}


def _is_shouting(text: str) -> bool:
    """Tamamı büyük harfle yazılmış başlık.

    Böyle bir metinde her kelime ticker gibi görünür, dolayısıyla büyük harf
    bir sinyal olmaktan çıkar. Ticker eşleşmesi bu durumda atlanır; ad
    eşleşmesi çalışmaya devam eder.
    """
    letters = [c for c in (text or "") if c.isalpha()]
    if len(letters) < 12:
        return False
    return sum(1 for c in letters if c.isupper()) / len(letters) > 0.9


def resolve_symbols(
    text: str,
    universe: Iterable[Any],
    ticker_markets: Optional[set[str]] = None,
) -> list[dict[str, str]]:
    """Metnin bahsettiği sembolleri, neye dayandığıyla birlikte döner.

    `universe`: `symbol` ve `name` taşıyan kayıtlar (sözlük ya da nesne).
    Dönen: `[{"symbol": "THYAO", "basis": "NAME"}]`, sembole göre sıralı.

    İki yol var ve ikisi de tam eşleşme ister; hiçbiri bulanık değil:

    * **SYMBOL** -- kod, metinde BÜYÜK HARFLE ve tek başına geçiyor.
    * **NAME** -- resmî unvanın çekirdeği, metinde olduğu gibi geçiyor.
    * **ALIAS** -- elle yazılmış ticari kısa ad (`ALIASES`). Haber "Aselsan"
      yazıyor, unvan "ASELSAN ELEKTRONİK SANAYİ VE TİCARET A.Ş."; NAME yolu
      bunu bulamaz. Liste elle, çünkü otomatik türetme ölçüldüğünde sıradan
      Türkçe kelimeleri şirket sanıyordu.
      "türk hava yollari", "turk hava yollari ndan rekor" içinde bulunur;
      kesme işareti boşluğa çevrildiği için Türkçe ekler eşleşmeyi bozmaz.
    `basis` ayrı ayrı raporlanıyor çünkü kanıt güçleri farklı: bir kod
    eşleşmesi kesin, ad eşleşmesi biraz daha zayıf. Yanlış bir bağ çıktığında
    hangi kuraldan geldiği okunabilir olmalı.

    Kısmi ad eşleşmesi YOK. "Garanti" araması "GARANTİ BBVA OPERASYONEL
    KİRALAMA" ile "TÜRKİYE GARANTİ BANKASI"nı birbirine karıştırırdı; ikisi
    ayrı şirket ve ikisinin haberi ayrı yere gider.

    `ticker_markets` verilirse KOD eşleşmesi yalnızca o piyasalardaki
    enstrümanlar için denenir; ad eşleşmesi her zaman tüm evrende çalışır.
    Hangi piyasa olduğu çağıranın kararı, çünkü bu bir dil/kaynak sorusu:
    Türkçe bir haber bir ABD şirketini kodyla değil adıyla anar. Ölçüldü --
    1.542 Türkçe haberde ABD kodu 7 kez eşleşti ve YEDİSİ DE yanlıştı
    (`MSCI` altı kez endeksin kendisi, `FAST` bir kez Türkiye'nin anlık ödeme
    sistemi); aynı korpusta BIST kodu 8 kez eşleşti ve hepsi doğruydu.
    """
    plain = strip_markup(text)
    folded_text = f" {fold(plain)} "
    # Kısa adlar evrene bakmadan aranıyor: liste zaten sembol taşıyor ve
    # evreni bir kez daha dolaşmak aynı işi iki kez yapmak olurdu.
    alias_hits = {
        symbol: alias
        for alias, symbol in _ALIAS_INDEX.items()
        if f" {alias} " in folded_text
    }
    # Ticker taraması da temizlenmiş metin üzerinde: `<IMG SRC=...>` gibi
    # bir etiket büyük harfli, tek başına duran "kelimeler" üretir.
    tokens = set() if _is_shouting(plain) else _ticker_tokens(plain)

    found: dict[str, str] = {}
    # Evrende OLMAYAN bir kısa ad kabul edilmiyor: liste elle yazıldığı için
    # bir sembol borsadan çıktığında ya da yanlış yazıldığında burada
    # sessizce hayalet bir bağ üretebilirdi.
    known = {(_get(row, "symbol") or "").strip().upper() for row in universe}
    for symbol, alias in alias_hits.items():
        if symbol in known and not _shadowed(alias, symbol, universe, folded_text):
            found[symbol] = "ALIAS"

    for row in universe:
        symbol = (_get(row, "symbol") or "").strip().upper()
        if not symbol:
            continue

        # Kod eşleşmesi kısa addan GÜÇLÜ: aynı sembol her ikisiyle de
        # bulunduysa kanıtın güçlüsü yazılır.
        if (
            len(symbol) >= MIN_TICKER_LENGTH
            and symbol in tokens
            and (ticker_markets is None or _get(row, "market") in ticker_markets)
        ):
            found[symbol] = "SYMBOL"
            continue

        core = core_name(_get(row, "name") or "")
        # Sembolün kendisi ad olarak saklanmışsa (BIST satırları öyle
        # tohumlanmıştı) ad eşleşmesi anlamsızdır: zaten ticker yolu var.
        if not core or core == symbol.lower():
            continue
        # Tek kelimelik ve kısa bir çekirdek ad ("logo", "mavi") sıradan
        # metinde geçer, dolayısıyla bir şirketi göstermez. Böyle bir satır
        # yalnızca kod yoluyla bulunur.
        if " " not in core and len(core) < MIN_NAME_LENGTH:
            continue

        if f" {core} " in folded_text:
            found[symbol] = "NAME"

    return [
        {"symbol": symbol, "basis": basis}
        for symbol, basis in sorted(found.items())
    ]


def _shadowed(
    alias: str, symbol: str, universe: Iterable[Any], folded_text: str
) -> bool:
    """Kısa ad, metindeki DAHA UZUN bir resmî adın parçası mı.

    "Garanti BBVA Operasyonel Kiralama" ayrı bir şirket ve "garanti bbva"
    kısa adı onu bankaya bağlardı. Metinde kısa adı İÇEREN başka bir
    şirketin resmî adı varsa, kısa ad susuyor: o haberi doğru şirkete
    bağlamak NAME yolunun işi ve kanıtı daha güçlü.

    Bu modülün kuralı: kaçırmak, yanlış bağlamaktan iyidir.
    """
    for row in universe:
        other = (_get(row, "symbol") or "").strip().upper()
        if other == symbol:
            continue
        core = core_name(_get(row, "name") or "")
        if core and alias in core and f" {core} " in folded_text:
            return True
    return False


_ALIAS_INDEX = _build_alias_index()


def _get(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)
