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
