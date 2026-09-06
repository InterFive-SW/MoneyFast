# TEFAS — Türk yatırım fonları

`Fonlar` ekranı `MOCK_FUNDS` üzerinden çiziliyordu ve üstünde "Örnek veri"
uyarısı vardı. Bu belge onu gerçek veriyle değiştiren entegrasyonu ve
**bilinçli olarak alınmış bir kararı** kaydediyor.

## Karar: robots.txt istisnası

`https://www.tefas.gov.tr/robots.txt` şunu diyor:

```
User-Agent: *
Disallow: /api/
...
User-Agent: anthropic-ai
Disallow: /private-content/
Disallow: /api/
```

Fon verisi **yalnızca** `/api/` altından geliyor. Sayfalar istemcide çizilen
bir Next.js kabuğu (`/_next/` de ayrıca yasaklı), dolayısıyla izin verilen
bir yol üzerinden aynı veriye ulaşmanın yolu yok.

**Karar ürün sahibinindir (5 Eylül 2026).** Alternatifler sunuldu — BIST'te
işlem gören borsa yatırım fonlarıyla yetinmek, ya da TEFAS/Takasbank'tan
yazılı izin istemek — ve `/api/`ye gitmek seçildi.

Karar sessizce uygulanmadı. `courtesy.ROBOTS_EXEMPT_HOSTS` içinde tek girdi
olarak, adıyla duruyor; bir gözden geçiren onu görüyor. Muafiyet her turda
loglanıyor. Ve tur **varsayılan olarak KAPALI**: `INGESTOR_TEFAS_ENABLED`
açıkça `1` yapılmadıkça çalışmıyor, çünkü klonlayan bir ekip arkadaşının
farkında olmadan devreye sokması doğru olmaz.

### Koşullar

* Dürüst `User-Agent`: projeyi adlandırıyor ve bağlantı veriyor. Tarayıcı
  taklidi YOK.
* `Origin` ve `Referer` gönderilmiyor. İkisi de *"bu istek sizin
  sitenizdeki bir sayfadan geldi"* iddiası ve bu doğru değil. Ölçüldü:
  zaten fark etmiyorlar.
* **Günde bir tur** (20:30). NAV günde bir yayımlanıyor; daha sık yoklamanın
  getirisi yok, maliyeti var.
* İstekler arası en az iki saniye, ve fon başına iş bütçeyle sınırlı.
* **403 ya da bir doğrulama ekranı gelirse bu DURMAK için sinyaldir.**
  Yeniden deneme, başlık değiştirme, vekil sunucu, oturum ısıtma yok.
  Ticarileşme hâlinde bu karar yeniden verilmelidir.

## Uçlar

Hepsi **POST**. Kütüphanelerin belgelediği biçim ölü; denendi:

```
GET  /api/funds/fonGnlBlgSiraliGetir   404  ERR-006 "Method not found or disabled!"
POST /api/DB/BindHistoryInfo            404  ERR-006 "Method not found or disabled!"
```

Aşağıdakiler tarayıcıdan alınan bir HAR kaydından çıkarıldı — tahmin değil.

| uç | gövde | verdiği |
|---|---|---|
| `funds/fonUnvanAra` | `{dil, aramaMetni:"", fonTip:null}` | **2.602 fonun** kodu ve unvanı, TEK istekte |
| `statistics/tefas/getFplFonList` | `{}` | kurucu (`kurucuAd`), operatör, durum |
| `funds/fonGnlBlgSiraliGetir` | `{fonTipi, basTarih, bitTarih, basSira, bitSira, dil}` | fiyat, portföy büyüklüğü, kişi sayısı |
| `funds/fonFiyatBilgiGetir` | `{fonKodu, dil, periyod}` | NAV serisi, kategori derecesi |
| `funds/fonProfilDtyGetir` | `{dil, fonKodu, periyod}` | şemsiye türü (`fonTuru`) |

`basTarih == bitTarih` veriliyor: aralık verilince uç fon × gün kadar satır
döndürüyor (ölçüldü, bir aylık aralıkta `toplamSayi` **46.285**).

Ağ geçidi hatayı **200 ile ve gövdede** döndürebiliyor — ölçüldü:
`{"errorCode": null, "errorMessage": "Index 0 out of bounds for length 0"}`.
Yalnızca durum koduna bakan bir istemci bunu boş sonuç sanardı.

## Arayüzün istediği ama TEFAS'ın VERMEDİĞİ alanlar

HAR'daki her yanıtın alan adları tarandı — 85 ayrı alan. Şunlar **yok**:

* yönetim ücreti
* stopaj
* risk değeri (1–7)
* hisse bazında portföy dağılımı
* net giriş/çıkış

`dagilimSiraliGetirT` varlık **sınıfı** yüzdeleri veriyor (`dt`, `fb`,
`kkstl`, `osks`, `ost`, `tr`, `vdm`, `vmtl`…) ama sütun etiketleri HAR'da
yok, dolayısıyla hangi kodun hangi varlık sınıfı olduğu tahmine kalıyor.
Tahmin edilmedi.

Bu alanlar **uydurulmadı ve sütunları açılmadı**. Deponun kendi kuralı:
*"aracın hiç döndürmediği bir alan için `veri yok` kullanılmaz, o sütun hiç
yazılmaz."* Boş bir sütun, bir gün dolacakmış gibi duran bir söz olurdu.
Karşılığı olan alanlar ekranda kaldı, olmayanlar kaldırıldı.

Bu alanlar isteniyorsa iki yol var: fonun KAP'taki izahnamesi (yönetim
ücreti orada yazılı), ya da TEFAS'ın fon detay ekranından ikinci bir HAR.

## Bilinen durum (5 Eylül 2026)

Entegrasyon yazıldı ve testleri geçiyor, ama **uçtan uca doğrulanamadı**:
o gün TEFAS'ın API'si her uç için `{"error":"Proxy request failed"}` (HTTP
500) döndürmeye başladı. Bu bizimle ilgili bir engelleme değil —

* aynı cevap tarayıcı `User-Agent`'ı ile de geliyor,
* `Origin`/`Referer` eklemek değiştirmiyor,
* sitenin kendi sayfası HTTP 200 dönüyor,
* aynı sabah aynı uç temiz bir JSON (`ERR-006`) döndürüyordu.

Yani ağ geçidi ayakta, arkasındaki servis değil. Kaynak bu durumu ayrı
logluyor (`upstream unavailable`) ve tur yarın yeniden deniyor. API geri
geldiğinde doğrulanacak ilk şey: fon sayısının TEFAS'ın kendi ekranındaki
"2.041 sonuç bulundu" ifadesiyle karşılaştırılması.

## Fon geçmişi tohumlanıyor

Fon getirileri seriden **hesaplanıyor**, saklanmıyor (`market/funds.py`).
Yani NAV serisi olmayan bir fonun her getiri sütunu `NA` görünüyor — ve seri
fon BAŞINA bir istek. Ölçülen: tek istek beş yılı veriyor (`periyod: 60`,
1.258 satır), dolayısıyla sorun derinlik değil, 2.602 isteğin süresi; 5
saniyelik aralıkla ~3,6 saat.

`ingestor/backfill_funds.py` bunu 25'lik parçalar hâlinde ve kaldığı yerden
devam ederek yapıyor. Sonuç `seeds/market/funds.csv.gz` (evren) ve
`seeds/market/fund_prices.csv.gz` (bir yıllık NAV) olarak commit'leniyor;
`scripts/export_market.py` yazıyor, `scripts/load_market.py` her açılışta
teklif ediyor. Mumlarla aynı yol: geçici tabloya `COPY`, sonra tek
`INSERT ... ON CONFLICT DO NOTHING`, ve künyedeki satır sayısı "zaten dolu"
demeyi mümkün kılıyor.

Bir yıl, beş değil: beş yılın tamamı ~3,2 milyon satır ve bu, bir klonun
açılışta ihtiyaç duyduğu ZEMİN değil — toplayıcı üstüne çıkıyor.

**Pre-commit hook'una BAĞLI DEĞİL.** Kullanıcı tohumları her commit'te
yeniden yazılıyor; bu ise elle üretilen bir arşiv ve gzip blob'u
delta'lanmadığı için her yeniden yazma kalıcı geçmiş demek (KAP gövdelerinde
alınan kararın aynısı).

## Fon almak

Fonlar bir dönem hiç alınamıyordu: `transaction_proposals.symbol`
`investment.investment_products` (`symbol`) üzerinden çözülüyor, fonlar ise
`market.funds` (`code`) içinde — iki ayrı evren.

Köprü **ilk emirde** kuruluyor (`funds.ensure_tradable`), toptan değil:
2.602 fonu enstrüman evrenine yazmak, Piyasalar ekranını ve enstrüman
listesini kimsenin aramadığı fon kodlarıyla doldururdu, ve Fonlar ekranı
zaten var. Yazılan satır `product_type='fund'`, `market='TEFAS'` ve
`data_symbol=NULL` taşıyor — sonuncusu "bunu fiyatlamaya çalışma" demek,
çünkü yfinance bir TEFAS kodunu fiyatlayamaz.

Fiyat `funds.sync_quotes` ile `market_quotes`a yansıtılıyor, yalnızca
köprülenmiş fonlar için. Böylece portföy değerlemesi, pozisyon satırı, risk
ve emir eşleştirme yollarının hepsi olduğu gibi çalışıyor; paralel bir
fon-emri yolu yazmak `settle`i ikinci kez yazmak olurdu.

**Fon limit emri günde bir kez kontrol ediliyor** — NAV günde bir
yayımlanıyor ve gün içi fiyat yok. Bu bir hata değil, ürünün doğası; arayüz
ve sohbet ikisi de bunu yazıyor, yoksa emrin donduğu sanılır.


## `fonProfilDtyGetir` sanıldığı şeyi döndürmüyor

Ölçüldü ve düzeltildi. O uç fonun profilini değil, **karşılaştırma
grafiğinin gösterge listesini** döndürüyor:

```json
{"fonKodu": "ALTIN",   "fonTuru": "ALTIN",   "fonTurGetiri": 0.466166}
{"fonKodu": "BIST100", "fonTuru": "BIST100", "fonTurGetiri": 0.286596}
{"fonKodu": "BIST30",  "fonTuru": "BIST30",  "fonTurGetiri": 0.383213}
```

Yanıt **her fon için aynı** — `fonKodu` istenen fonu değil, göstergeyi
adlandırıyor. Toplayıcı ilk satırın `fonTuru`sunu şemsiye türü,
`fonTurGetiri`sini kategori getirisi sanıyordu. Sonuç: 1.054 aktif fonun
1.021'i "ALTIN" şemsiyesine yazıldı ve hepsine aynı %46,6 kategori
getirisi kondu. Boş bir sütundan kötü — uydurulmuş bir değer doğruymuş
gibi süzülüyordu.

**Şemsiye türünün doğru kaynağı iki uçtan geliyor:**

| Uç | Ne verir |
|---|---|
| `POST /api/funds/fonTurGetir` | Şemsiye listesi: `sfonTuru` (id) → `sfonTurAciklama` (ad) |
| `POST /api/funds/fonGnlBlgSiraliGetir` + `sfonTurKod` | O şemsiyedeki fonlar |

Yani eşleme fon başına değil **şemsiye başına** bir istek: on iki şemsiye ×
fon tipi, 1.054 değil. `INGESTOR_TEFAS_PROFILE_BUDGET` bu yüzden kalktı —
dilimlenecek bir şey yok.

**Süzgeç her fon tipinde uygulanmıyor ve bu ölçülüyor.** `YAT`'ta
`sfonTurKod` gerçekten süzüyor (Borçlanma 85, Hisse 192, Para Piyasası 81,
sıfır kesişim). `EMK` ve `BYF`'de süzülmüyor: aynı fon (`AAJ`, `BLH`) her
turda iki farklı şemsiyede birden dönüyor. Bir fon tipi içinde çakışma
görüldüğünde **o tipin tamamı bırakılıyor** — yalnızca çakışan fonu
düşürmek, aynı hatalı listenin geri kalanını doğruymuş gibi yazardı.

Kısıtlanan (429) tek bir şemsiye ise yalnızca kendini düşürüyor, tipi
değil: listeler bağımsız, bir fon yalnızca göründüğü listeden ad alıyor.
Tipin tamamını bırakmak, tek bir sayfa yüzünden on bir doğru şemsiyeyi de
atmak demekti — ölçüldü, bir turda `YAT`'ın tamamı bu yüzden kayboldu.
Kısıtlanan sayfa bir kez, otuz saniye sonra yeniden deneniyor; ısrar
ederse o şemsiye bir sonraki tura kalıyor.

Sonuç (6 Eylül 2026): 1.054 aktif fonun **1.052'sinde** şemsiye türü dolu,
dokuz şemsiye adı altında. Kalan iki fon `EMK`/`BYF` tarafında.

**`category_return` sütunu düştü** (migration 0041). Doğru kaynağı yok:
gösterge listesi fonun kategorisiyle eşleşmiyor ve TEFAS'ın döndürdüğü
hiçbir alan "kategorinin ortalama getirisi" değil. Kategori **sırası**
(`category_rank` / `category_size`) gerçek ve kalıyor; "1.333 fon içinde
751." zaten aynı soruyu cevaplıyor.
