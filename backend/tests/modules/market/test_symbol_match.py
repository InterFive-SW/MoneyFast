"""Haber–hisse eşleştirmesi.

Buradaki testlerin çoğu tek bir özelliği koruyor: **kaçırmak, yanlış
bağlamaktan iyidir.** Eşleşmeyen bir haber yalnızca listede görünmez; yanlış
eşleşen bir haber, kullanıcıya sahip olmadığı bir şirket hakkında bilgi
veriyormuş gibi görünür ve fark edilmesi çok daha zordur.
"""

from __future__ import annotations

import pytest

from app.modules.market import symbol_match

#: Gerçek unvanlar, KAP üye listesinden. Sahte veri kullanmıyoruz çünkü
#: eşleştirmenin zor kısmı tam da bu unvanların biçimi.
UNIVERSE = [
    {"symbol": "THYAO", "name": "TÜRK HAVA YOLLARI A.O."},
    {"symbol": "GARAN", "name": "TÜRKİYE GARANTİ BANKASI A.Ş."},
    {"symbol": "ASELS", "name": "ASELSAN ELEKTRONİK SANAYİ VE TİCARET A.Ş."},
    {"symbol": "TUPRS", "name": "TÜPRAŞ-TÜRKİYE PETROL RAFİNERİLERİ A.Ş."},
    {"symbol": "LOGO", "name": "LOGO YAZILIM SANAYİ VE TİCARET A.Ş."},
    {"symbol": "SASA", "name": "SASA POLYESTER SANAYİ A.Ş."},
    {"symbol": "TCELL", "name": "TURKCELL İLETİŞİM HİZMETLERİ A.Ş."},
    {"symbol": "VESTL", "name": "VESTEL ELEKTRONİK SANAYİ VE TİCARET A.Ş."},
    # Adı hiç çözülmemiş bir satır: eski tohumda name = sembol.
    {"symbol": "KOZAL", "name": "KOZAL"},
]


class TestStripMarkup:
    """Haber özetleri beslemeden işaretlemeyle geliyor.

    Bu metin hem eşleştirmeye hem ekrana gidiyor, ve daha önemlisi ingestor
    onu RAG'a `content` olarak gönderiyor -- ölçüldü, korpustaki 1.533
    parçanın 917'si işaretleme taşıyordu, yani gömme vektörleri haberin metni
    yerine HTML gürültüsünü de temsil ediyordu.
    """

    def test_a_tag_is_removed_whole(self):
        """Etiketin İÇİ değil KENDİSİ gider: `align` bir öznitelik adı ve
        temizlenmediğinde Align Technology'ye (ALGN) eşleşiyordu."""
        assert symbol_match.strip_markup(
            '<img align="right" src="https://img.example.com/a.jpg" />Zam geldi.'
        ) == "Zam geldi."

    def test_entities_are_decoded_not_deleted(self):
        """Silinseydi "Türkiye nin" kalırdı."""
        assert symbol_match.strip_markup("Türkiye&#039;nin ihracatı") == (
            "Türkiye'nin ihracatı"
        )

    def test_a_double_escaped_entity_needs_the_second_pass(self):
        """Ölçülen veride `LPG&amp;#039;nin` var: besleme çift kaçışlı
        gönderiyor ve tek geçiş `&#039;`de bırakıyor."""
        assert symbol_match.strip_markup("LPG&amp;#039;nin") == "LPG'nin"

    def test_the_passes_stop_at_two(self):
        """Üç kat kaçışlı bir metin iki geçişte tam çözülmez ve bu KASITLI:
        döngü sabit sayıda, çünkü "kararlı hâle gelene kadar çöz" kuralı
        metnin içindeki gerçek bir `&amp;` dizisini de eritirdi."""
        assert symbol_match.strip_markup("&amp;amp;#039;") == "&#039;"

    def test_whitespace_is_collapsed(self):
        assert symbol_match.strip_markup("bir\n\n  iki") == "bir iki"

    def test_empty_input_is_safe(self):
        assert symbol_match.strip_markup("") == ""
        assert symbol_match.strip_markup(None) == ""


class TestFold:
    def test_turkish_letters_collapse_to_ascii(self):
        """Aynı isim üç farklı yazımla gelir: TÜPRAŞ, Tüpraş, TUPRAS."""
        assert symbol_match.fold("TÜPRAŞ") == symbol_match.fold("Tüpraş")
        assert symbol_match.fold("TÜPRAŞ") == "tupras"

    def test_dotted_and_dotless_i_are_one(self):
        assert symbol_match.fold("İŞ") == symbol_match.fold("iş") == "is"

    def test_apostrophes_become_spaces(self):
        """Kesme işareti Türkçede eki ayırır; boşluğa çevrilince çekirdek ad
        yine bir alt dize olarak bulunabilir."""
        assert symbol_match.fold("Aselsan'ın") == "aselsan in"


class TestCoreName:
    def test_legal_suffix_is_stripped(self):
        """Hiçbir haber başlığı "A.O." yazmaz."""
        assert symbol_match.core_name("TÜRK HAVA YOLLARI A.O.") == "turk hava yollari"
        assert symbol_match.core_name("AKBANK T.A.Ş.") == "akbank"
        assert symbol_match.core_name("ASELSAN ELEKTRONİK SANAYİ VE TİCARET A.Ş.") == (
            "aselsan elektronik sanayi ve ticaret"
        )

    def test_punctuation_inside_the_name_survives_as_a_space(self):
        assert symbol_match.core_name("TÜPRAŞ-TÜRKİYE PETROL RAFİNERİLERİ A.Ş.") == (
            "tupras turkiye petrol rafinerileri"
        )

    def test_holding_is_part_of_the_name_not_a_legal_suffix(self):
        """Sonek sayıldığında "KOÇ HOLDİNG A.Ş." çekirdeği "koc"a iniyordu --
        üç harf, hiçbir yoldan eşleşmez, dolayısıyla Koç Holding haberleri
        hep kaçıyordu. Ölçüldü: bu düzeltme 401 başlıkta 39'dan 42'ye çıkardı.
        """
        assert symbol_match.core_name("KOÇ HOLDİNG A.Ş.") == "koc holding"

    def test_an_empty_name_is_safe(self):
        assert symbol_match.core_name("") == ""
        assert symbol_match.core_name(None) == ""


class TestNameMatching:
    def test_a_company_name_with_a_turkish_suffix_matches(self):
        """Asıl kazanılan dava: haber "THYAO" değil "Türk Hava Yolları" yazar."""
        found = symbol_match.resolve_symbols(
            "Türk Hava Yolları'ndan rekor yolcu sayısı", UNIVERSE
        )
        assert found == [{"symbol": "THYAO", "basis": "NAME"}]

    def test_a_sector_mention_matches_nothing(self):
        """"hava yolları sektörü" hiçbir şirkete bağlanmamalı."""
        assert symbol_match.resolve_symbols(
            "Hava yolları sektöründe kapasite artışı bekleniyor", UNIVERSE
        ) == []

    def test_a_different_company_with_a_shared_word_is_not_matched(self):
        """KAP listesinde "GARANTİ BBVA OPERASYONEL KİRALAMA" da var ve
        "TÜRKİYE GARANTİ BANKASI"ndan ayrı bir şirket. Kısmi ad eşleşmesi
        ikisini birbirine karıştırırdı."""
        assert symbol_match.resolve_symbols(
            "Garanti BBVA Operasyonel Kiralama'dan yeni filo yatırımı", UNIVERSE
        ) == []

    def test_a_one_word_short_name_is_not_matched_loosely(self):
        """"logo" sıradan metinde geçer; tek kelimelik kısa çekirdek adlar
        ad yoluyla eşleşmez."""
        assert symbol_match.resolve_symbols(
            "Şirketin yeni logo tasarımı tanıtıldı", UNIVERSE
        ) == []

    def test_a_name_stored_as_its_own_ticker_never_matches_by_name(self):
        """Eski tohumda BIST satırlarının adı sembolün kendisiydi. Böyle bir
        satırda ad eşleşmesi anlamsız -- zaten ticker yolu var."""
        found = symbol_match.resolve_symbols("kozal hakkında bir haber", UNIVERSE)
        assert found == []

    def test_case_and_diacritics_do_not_matter(self):
        assert symbol_match.resolve_symbols(
            "TUPRAS TURKIYE PETROL RAFINERILERI ilk çeyrek sonuçları", UNIVERSE
        ) == [{"symbol": "TUPRS", "basis": "NAME"}]


class TestTickerMatching:
    def test_an_uppercase_standalone_code_matches(self):
        found = symbol_match.resolve_symbols(
            "Borsada bugün: ASELS yüzde 3 yükseldi", UNIVERSE
        )
        assert found == [{"symbol": "ASELS", "basis": "SYMBOL"}]

    def test_a_lowercase_code_does_not_match(self):
        """"sasa" küçük harfle sıradan bir metinde geçebilir."""
        assert symbol_match.resolve_symbols("sasa hakkında bir şey", UNIVERSE) == []

    def test_a_code_inside_a_longer_word_does_not_match(self):
        assert symbol_match.resolve_symbols("ASELSANIN yeni sözleşmesi", UNIVERSE) == []

    def test_an_all_caps_headline_disables_ticker_matching(self):
        """Tamamı büyük harf yazılmış bir başlıkta her kelime ticker gibi
        görünür, yani büyük harf bir sinyal olmaktan çıkar. Ad eşleşmesi
        çalışmaya devam eder."""
        found = symbol_match.resolve_symbols(
            "BORSA İSTANBUL'DA SASA VE ASELS HAREKETLİ BİR GÜN GEÇİRDİ", UNIVERSE
        )
        assert found == []

    def test_a_name_still_resolves_inside_a_shouted_headline(self):
        found = symbol_match.resolve_symbols(
            "TÜRK HAVA YOLLARI YENİ UÇAK SİPARİŞİNİ AÇIKLADI BUGÜN", UNIVERSE
        )
        assert found == [{"symbol": "THYAO", "basis": "NAME"}]


class TestTickerMarketRestriction:
    """Kod eşleşmesi hangi piyasalarda denenir.

    Türkçe bir haber bir ABD şirketini kodyla değil adıyla anar; ABD kodları
    ise Türkçe kısaltmalarla çakışıyor. Ölçüldü: 1.542 Türkçe haberde ABD
    kodu 7 kez eşleşti ve YEDİSİ DE yanlıştı -- `MSCI` altı kez endeksin
    kendisi, `FAST` bir kez Türkiye'nin anlık ödeme sistemi. Aynı korpusta
    BIST kodu 8 kez eşleşti ve hepsi doğruydu.
    """

    ROWS = [
        {"symbol": "HALKB", "name": "Türkiye Halk Bankası A.Ş.", "market": "BIST"},
        {"symbol": "FAST", "name": "Fastenal Company", "market": "NASDAQ"},
        {"symbol": "MSCI", "name": "MSCI Inc.", "market": "NYSE"},
    ]

    def test_a_local_ticker_matches(self):
        assert symbol_match.resolve_symbols(
            "ABD'deki dava sonrası HALKB hisseleri", self.ROWS, {"BIST"}
        ) == [{"symbol": "HALKB", "basis": "SYMBOL"}]

    def test_a_foreign_ticker_does_not(self):
        """"FAST işlem tutar limitleri" Türkiye'nin ödeme sistemi hakkında;
        Fastenal ile ilgisi yok."""
        assert symbol_match.resolve_symbols(
            "FAST işlem tutar limitleri değişiyor", self.ROWS, {"BIST"}
        ) == []
        assert symbol_match.resolve_symbols(
            "MSCI Türkiye kararını değiştirdi", self.ROWS, {"BIST"}
        ) == []

    def test_a_foreign_company_still_matches_by_name(self):
        """Kısıt yalnızca KOD yolunda: Türkçe haber ABD şirketini adıyla anar
        ve o eşleşme değerli."""
        assert symbol_match.resolve_symbols(
            "Fastenal Company çeyrek sonuçlarını açıkladı", self.ROWS, {"BIST"}
        ) == [{"symbol": "FAST", "basis": "NAME"}]

    def test_without_a_restriction_every_market_matches_by_ticker(self):
        assert symbol_match.resolve_symbols(
            "FAST işlem tutar limitleri değişiyor", self.ROWS
        ) == [{"symbol": "FAST", "basis": "SYMBOL"}]

    def test_a_row_without_a_market_is_refused_when_a_restriction_is_given(self):
        """Piyasası bilinmeyen bir satır, kısıt varken koddan eşleşmez --
        bilinmeyeni içeri almak kısıtı anlamsızlaştırırdı."""
        rows = [{"symbol": "HALKB", "name": "Türkiye Halk Bankası A.Ş."}]
        assert symbol_match.resolve_symbols("HALKB yükseldi", rows, {"BIST"}) == []


class TestMultipleAndEdges:
    def test_two_companies_in_one_story_both_resolve(self):
        found = symbol_match.resolve_symbols(
            "Türk Hava Yolları ve Aselsan Elektronik Sanayi ve Ticaret "
            "arasında iş birliği",
            UNIVERSE,
        )
        assert found == [
            {"symbol": "ASELS", "basis": "NAME"},
            {"symbol": "THYAO", "basis": "NAME"},
        ]

    def test_the_ticker_wins_when_both_would_match(self):
        """Aynı şirket iki yoldan bulunursa tek satır döner."""
        found = symbol_match.resolve_symbols(
            "ASELS — Aselsan Elektronik Sanayi ve Ticaret bilançosu", UNIVERSE
        )
        assert found == [{"symbol": "ASELS", "basis": "SYMBOL"}]

    def test_an_empty_text_resolves_nothing(self):
        assert symbol_match.resolve_symbols("", UNIVERSE) == []
        assert symbol_match.resolve_symbols(None, UNIVERSE) == []

    def test_an_empty_universe_resolves_nothing(self):
        assert symbol_match.resolve_symbols("Türk Hava Yolları", []) == []

    def test_a_universe_row_without_a_symbol_is_skipped(self):
        assert symbol_match.resolve_symbols(
            "Türk Hava Yolları", [{"symbol": "", "name": "TÜRK HAVA YOLLARI A.O."}]
        ) == []

    def test_objects_work_as_well_as_dicts(self):
        """Router evreni ORM satırı olarak geçirir."""
        from types import SimpleNamespace

        rows = [SimpleNamespace(symbol="THYAO", name="TÜRK HAVA YOLLARI A.O.")]
        assert symbol_match.resolve_symbols("Türk Hava Yolları'ndan", rows) == [
            {"symbol": "THYAO", "basis": "NAME"}
        ]


class TestHoldingNames:
    ROWS = [{"symbol": "KCHOL", "name": "KOÇ HOLDİNG A.Ş."}]

    def test_the_holding_resolves_by_its_full_name(self):
        assert symbol_match.resolve_symbols(
            "Koç Holding'den yeni yatırım", self.ROWS
        ) == [{"symbol": "KCHOL", "basis": "NAME"}]

    def test_the_bare_word_does_not_resolve(self):
        """"koç" Türkçede sıradan bir kelime -- burç adı, hayvan, soyadı."""
        assert symbol_match.resolve_symbols(
            "Bu hafta koç burcu yorumu", self.ROWS
        ) == []


class TestShortNamesNeverMatchLoosely:
    def test_a_short_single_word_company_resolves_to_nothing(self):
        """Ne ad ne de kısa ad yolundan geçer: dört harflik bir kelime
        sıradan metinde geçer ve bağlanırsa fark edilmesi zor bir hata olur.

        Kaçırmak burada doğru davranış -- kullanıcı bir haberi görmez, ama
        sahip olmadığı bir şirketin haberini de görmez.
        """
        rows = [{"symbol": "MAVI", "name": "MAVİ A.Ş."}]
        assert symbol_match.resolve_symbols("mavi bir gökyüzü", rows) == []

    def test_a_short_name_that_differs_from_the_ticker_is_also_refused(self):
        """KAP'ın 1.225 üyesinin hiçbiri bugün bu şekilde değil -- ama yeni
        halka arz olan "ETİ A.Ş." gibi bir ad, sıradan metindeki "eti"
        kelimesine bağlanırdı. Koruma bu yüzden var, bugünkü veri için değil.
        """
        rows = [{"symbol": "ETIYE", "name": "ETİ A.Ş."}]
        assert symbol_match.resolve_symbols("eti tüketimi arttı", rows) == []
        # Kod yolu yine çalışıyor.
        assert symbol_match.resolve_symbols("ETIYE bugün yükseldi", rows) == [
            {"symbol": "ETIYE", "basis": "SYMBOL"}
        ]

    def test_the_ticker_path_still_works_for_such_a_company(self):
        """Kod BÜYÜK HARFLE geçtiğinde eşleşme yine kurulur."""
        rows = [{"symbol": "MAVI", "name": "MAVİ A.Ş."}]
        assert symbol_match.resolve_symbols("MAVI bugün yükseldi", rows) == [
            {"symbol": "MAVI", "basis": "SYMBOL"}
        ]


#: Gölgeleme testleri için: aynı kısa adı içeren AYRI bir şirket.
SHADOW_UNIVERSE = UNIVERSE + [
    {"symbol": "GRNYO", "name": "GARANTİ BANKASI OPERASYONEL KİRALAMA A.Ş."},
]


class TestAliases:
    """Elle yazılmış ticari kısa adlar.

    Otomatik türetme DENENDİ VE ÖLÇÜLDÜ: resmî unvanın ilk kelimesini kısa ad
    saymak korpusta felaket üretiyor -- `turkiye` 551 haberde geçiyor ve sekiz
    bankaya bağlanırdı, `altin` 112, `izmir` 21, `zorlu` 8. Yüksek frekanslı
    tokenların neredeyse tamamı sıradan Türkçe kelime.

    Bu yüzden liste elle ve tek kurala göre: bir kısa ad, ancak YALNIZCA o
    şirketi gösteriyorsa girer.
    """

    def test_a_trade_name_the_official_title_does_not_carry(self):
        """"ASELSAN ELEKTRONİK SANAYİ VE TİCARET A.Ş." çekirdeği "aselsan
        elektronik sanayi ve ticaret"; haber sadece "Aselsan" yazıyor ve NAME
        yolu bunu bulamıyor."""
        got = symbol_match.resolve_symbols(
            "Aselsan'dan yeni sözleşme", UNIVERSE
        )
        assert got == [{"symbol": "ASELS", "basis": "ALIAS"}]

    def test_turkish_suffixes_do_not_break_it(self):
        for text in ("Turkcell'in yeni yatırımı", "Turkcell’den açıklama",
                     "TURKCELL rekor kırdı"):
            got = symbol_match.resolve_symbols(text, UNIVERSE)
            assert {g["symbol"] for g in got} == {"TCELL"}, text

    def test_an_ordinary_word_is_not_an_alias(self):
        """Listeye giremeyen adlar: "zorlu" (sıfat), "emlak" (sıradan ad),
        "altin", "izmir". Ölçülen yanlış eşleşmeler bunlardı."""
        for text in ("Haakon'un zorlu sınavı", "Emlak vergisi düzenlemesi",
                     "İzmir'de kongre", "Altın fiyatları yükseldi"):
            assert symbol_match.resolve_symbols(text, UNIVERSE) == [], text

    def test_a_symbol_outside_the_universe_is_not_invented(self):
        """Liste elle yazılıyor: bir sembol borsadan çıktığında ya da yanlış
        yazıldığında burada hayalet bir bağ üretilmemeli."""
        assert symbol_match.resolve_symbols(
            "Aselsan'dan yeni sözleşme", [{"symbol": "THYAO", "name": "TÜRK HAVA YOLLARI A.O."}]
        ) == []

    def test_a_longer_official_name_shadows_the_alias(self):
        """"Garanti Bankası Operasyonel Kiralama" AYRI bir şirket. Metinde
        kısa adı içeren daha uzun bir resmî ad varsa kısa ad susuyor:
        kaçırmak, yanlış bağlamaktan iyidir."""
        got = symbol_match.resolve_symbols(
            "Garanti Bankası Operasyonel Kiralama'dan yeni filo yatırımı",
            SHADOW_UNIVERSE,
        )
        assert {g["symbol"] for g in got} == {"GRNYO"}

    def test_the_bank_itself_still_matches(self):
        got = symbol_match.resolve_symbols(
            "Garanti Bankası'ndan sürdürülebilir tahvil ihracı", SHADOW_UNIVERSE
        )
        assert {g["symbol"] for g in got} == {"GARAN"}

    def test_a_symbol_match_outranks_an_alias(self):
        """Kod eşleşmesi kısa addan güçlü; aynı sembol ikisiyle de
        bulunduysa kanıtın güçlüsü raporlanır."""
        got = symbol_match.resolve_symbols(
            "TCELL kodlu Turkcell hissesi", UNIVERSE, ticker_markets=None
        )
        assert got == [{"symbol": "TCELL", "basis": "SYMBOL"}]

    def test_no_alias_is_written_for_two_symbols(self):
        """Çakışan bir kısa ad sessizce birini ezerdi; kurulumda hata
        veriyor."""
        assert symbol_match._build_alias_index()

    def test_every_alias_is_folded_form(self):
        """Liste katlanmış biçimde yazılmalı: eşleştirme katlanmış metinde
        arıyor ve "Tüpraş" yazılmış bir kısa ad hiç tutmazdı."""
        for alias in symbol_match._ALIAS_INDEX:
            assert alias == symbol_match.fold(alias), alias


class TestAliasTableIsChecked:
    """Kısa ad tablosu elle yazılıyor; çakışma sessiz kalmamalı.

    İki şirkete aynı kısa adı yazmak, tabloyu büyüten birinin yapabileceği
    en kolay hata. Sözlük onu sessizce ezerdi: sonradan yazılan kazanır ve
    önceki şirketin haberleri, hiç uyarı vermeden başka bir sembole
    etiketlenirdi. Yanlış etiket, eksik etiketten kötü -- kullanıcı ASELS
    sorup THYAO haberi okur ve bunun yanlış olduğunu anlamasının bir yolu
    yoktur.
    """

    def test_the_same_name_written_to_two_symbols_is_an_error(self, monkeypatch):
        monkeypatch.setattr(
            symbol_match,
            "ALIASES",
            {"AAAA": ("ortak ad",), "BBBB": ("ortak ad",)},
        )
        with pytest.raises(ValueError, match="iki sembole birden"):
            symbol_match._build_alias_index()

    def test_the_same_name_repeated_for_one_symbol_is_fine(self, monkeypatch):
        """Aynı sembole iki kez yazmak gereksiz ama zararsız: çakışma değil."""
        monkeypatch.setattr(
            symbol_match, "ALIASES", {"AAAA": ("ortak ad", "ortak  ad")}
        )
        assert symbol_match._build_alias_index() == {"ortak ad": "AAAA"}

    def test_the_real_table_has_no_collisions(self):
        """Tablonun kendisi: bu test, koruma çalışsın diye değil, tablo
        bozulduğunda kırılsın diye var."""
        index = symbol_match._build_alias_index()
        assert len(index) == sum(len(v) for v in symbol_match.ALIASES.values())


class TestSpelledOutLegalSuffix:
    """Unvan eki açık yazıldığında da atılır.

    Ürün kayıtlarındaki resmî ad ile bildirim başlığındaki ad aynı eki farklı
    biçimde yazıyor: "Türkiye Vakiflar Bankasi Türk Anonim Ortakligi" ile
    "TÜRKİYE VAKIFLAR BANKASI T.A.O.". Yalnızca kısaltma atıldığı sürece bu
    ikisinin çekirdek adı farklı çıkıyor ve şirket kendi bildiriminde
    eşleşmiyordu.
    """

    @pytest.mark.parametrize(
        "written, core",
        [
            ("Türkiye Vakiflar Bankasi Türk Anonim Ortakligi", "turkiye vakiflar bankasi"),
            ("TÜRKİYE VAKIFLAR BANKASI T.A.O.", "turkiye vakiflar bankasi"),
            ("Teknosa Iç ve Dis Ticaret Anonim Sirketi", "teknosa ic ve dis ticaret"),
            ("TEKNOSA İÇ VE DIŞ TİCARET A.Ş.", "teknosa ic ve dis ticaret"),
        ],
    )
    def test_both_spellings_fold_to_the_same_core(self, written, core):
        assert symbol_match.core_name(written) == core

    def test_a_name_that_merely_contains_the_words_is_not_cut(self):
        """Ek yalnızca SONDA atılır: ortasında geçen bir kelime unvan eki
        değildir."""
        assert symbol_match.core_name("Anonim Sirketi Yatirim Holding") == (
            "anonim sirketi yatirim holding"
        )
