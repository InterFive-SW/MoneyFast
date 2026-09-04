# Küresel haber — GDELT

RSS beslemeleri ve KAP Türkiye'yi karşılıyor. İkisi de yurt dışında ne olup
bittiğini görmüyor, ve kullanıcının sorduğu zincir tam oradan başlıyor: bir
jeopolitik gelişme petrolü, petrol havayolunun yakıt maliyetini, o da
THYAO'yu etkiliyor. Zincirin ilk halkası derlemde yoksa geri kalanı tahmin
olur.

## Atıf — zorunlu

GDELT verisi **"unlimited and unrestricted use for any academic, commercial,
or governmental use of any kind without fee"** ile sunuluyor. Karşılığında
tek şey isteniyor ve bu bir nezaket değil, kullanım şartının kendisi:

> any use or redistribution of the data must include a citation to the GDELT
> Project and a link to this website.

Bu yüzden burada yazılı: **The GDELT Project — https://www.gdeltproject.org**

Küresel haber gösteren her yüzey bu atfı taşımalı. Kaldırmak, veriyi
kullanma iznini kaldırmak demek.

## Neden Context 2.0, DOC değil

İki uç var:

| uç | verdiği |
|---|---|
| `doc/doc?mode=artlist` | başlık, bağlantı, tarih, alan adı, dil |
| `context/context` | bunlara ek olarak **eşleşen cümle ve onu saran paragraf** |

Korpusa yalnızca başlık yazmak, "ABD'nin saldırısı petrolü nasıl etkiler"
sorusuna cevap veremeyen bir kayıt üretirdi: gömme vektörü on kelimeden
çıkarılamaz. `context` alanına ölçülen bir örnek:

> "UBI also said a rate hike in October could not be ruled out if the US
> Federal Reserve raises rates in September... It added that oil prices above
> USD 90 a barrel could increase inflation and pressure on the rupee, while
> easing geopolitical tensions could give the RBI more policy flexibility."

İkinci bir faydası var: **yayıncının kendi sayfası hiç çekilmiyor.** Metin
GDELT'in kendi indeksinden geliyor, dolayısıyla üçüncü tarafların
`robots.txt`leri sorusu hiç doğmuyor.

## Ölçülen sınırlar

Hiçbiri varsayılmadı; hepsi denendi ve uç noktanın kendi cevabıyla saptandı.

| sınır | kanıt |
|---|---|
| **istek başına 5 saniye** | 429 gövdesi: *"Please limit requests to one every 5 seconds"* |
| `timespan` ≤ 3 gün | `7d` -> *"The TIMESPAN is too large."* |
| `maxrecords` ≤ 200 | `250` -> *"A maximum of 200 records can be returned."* |
| yalnızca İngilizce | `sourcelang:turkish` -> *"Invalid/Unsupported Language"*; Türkçe ifade sorgusu boş `{}` |
| `robots.txt` yok | `api.gdeltproject.org/robots.txt` -> 404, yani teamül gereği izin |

İlk üçü düz metin olarak, **200 durum koduyla** dönüyor. JSON çözümlemesini
denemeden geçen bir istemci üçünü de sessizce "haber yok" diye okurdu; bu
yüzden `gdelt_source` JSON olmayan gövdeyi ayrıca yakalayıp logluyor.

Beş saniyelik sınır `courtesy.wait_for_host(..., minimum=5.0)` ile
uygulanıyor. Projenin genel gecikmesi 2 saniye; daha KISA olanı seçmek,
yazılı bir isteği sessizce çiğnemek olurdu.

## Sorgular

Şirket adı değil **mekanizma** seçildi. Bir Türk yatırımcının portföyünü
yurt dışından etkileyen şey tek tek yabancı şirketler değil, fiyat kanalları:
petrol (havayolu ve ulaştırma maliyeti), faiz ve enflasyon (değerleme ve kur),
jeopolitik ve tedarik zinciri (girdi maliyeti), çip ve savunma (BIST'te
doğrudan karşılığı olan iki sektör).

Liste `config.DEFAULT_GDELT_QUERIES` içinde ve bir BÜTÇE: sorgu başına bir
istek, istek başına beş saniye. Sekiz sorgu ~40 saniye demek, ve bu yüzden
küresel haber `run_news`ten ayrı bir iş (`global-news`, saatte bir) olarak
duruyor -- on beş dakikalık Türkçe haber döngüsünü bir dış servisin
temposuna bağlamamak için.

## Sembol etiketi

Bu süreçte veritabanı kredensiyeli yok, dolayısıyla sembol ÇIKARILMIYOR.
Öğeler `rss_source`in ürettiği sözlük biçiminde çıkıp aynı lavaboya akıyor;
backend `symbol_match` ile enstrüman evrenine karşı çözüyor. Küresel bir
haberde de BIST adı aranıyor ("Turkish Airlines" gibi), ama ölçülen isabet
düşük: 130 haberin 5'i etiketlendi.

Bu bir eksik değil, bilinen bir sınır: derlemin %53'ünde hiç sembol yok
(4.318 belgenin 2.285'i). Makro bir haberin zaten bir şirketi yoktur --
"petrol fiyatları" hiçbir hisseye ait değil ama havayollarının hepsini
ilgilendirir. Orkestratör bunu `_is_context` ile karşılıyor: etiketsiz bir
satır, daha yüksek bir puan barajını geçerse bağlam sayılıyor; BAŞKA bir
şirketin etiketini taşıyan satır ise puanı ne olursa olsun sayılmıyor.
