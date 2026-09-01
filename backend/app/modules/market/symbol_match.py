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
#: `&#039;` ve `&amp;` gibi varlıklar. Metne karışan `amp`, `quot`, `nbsp`
#: sözcükleri de eşleştirmeye girmemeli.
_HTML_ENTITY = re.compile(r"&[#a-zA-Z0-9]{2,8};")

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
#: Yakalamayı güvenle artırmanın yolu ELLE YAZILMIŞ bir kısa ad listesi
#: (`EREGL: erdemir`, `THYAO: thy`) -- bu depoda BIST ve Nasdaq üyelik
#: listelerinin yazıldığı biçimin aynısı: diff'te okunabilir, tarihli,
#: sessizce değişmeyen. Ayrı bir iş olarak duruyor.


def strip_markup(text: str) -> str:
    """HTML etiketlerini ve varlıklarını atar.

    Haber özetleri beslemeden işaretlemeyle geliyor. Etiketin İÇİ değil
    KENDİSİ atılıyor: `<img align="right" src="...">` tamamen gider, çünkü
    öznitelik adları ve URL'ler haberin metni değildir.
    """
    without_tags = _HTML_TAG.sub(" ", text or "")
    return _HTML_ENTITY.sub(" ", without_tags)


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
    # Ticker taraması da temizlenmiş metin üzerinde: `<IMG SRC=...>` gibi
    # bir etiket büyük harfli, tek başına duran "kelimeler" üretir.
    tokens = set() if _is_shouting(plain) else _ticker_tokens(plain)

    found: dict[str, str] = {}
    for row in universe:
        symbol = (_get(row, "symbol") or "").strip().upper()
        if not symbol:
            continue

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


def _get(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)
