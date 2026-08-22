# MoneyFast — Contract (Sözleşme) İş Akışı

Modüler monolite geçince "servisler arası sözleşme" sorunu büyük ölçüde ortadan
kalktı — modüller aynı process'te Python import'uyla konuşuyor, Pydantic tipleri
otomatik kontrol sağlıyor.

**Güncelleme:** Frontend backend'e birleşti (aynı image, aynı origin'den serve
ediliyor — bkz. MIMARI_KARARLAR.md). Bu yüzden backend↔frontend arasında artık
gerçek bir network sınırı yok, TypeScript tip üretimi opsiyonel hale geldi (frontend
zaten aynı repoda, backend'in Pydantic modellerine bakarak elle de yazılabilir,
isteyen `openapi-typescript` ile otomatik üretime devam edebilir). **Tek gerçek
sözleşme ihtiyacı backend↔ai-service sınırında kalıyor** — bu ikisi ayrı process,
ayrı container. Elle senkronize edilmiyor, backend'in ürettiği OpenAPI şemasından
**otomatik üretiliyor.**

## Temel prensip

Tek gerçek kaynak (source of truth): backend'in Pydantic modelleri → bunlardan
otomatik üretilen `/openapi.json`. Kimse frontend'de veya ai-service'te elle
"Transaction" tipi tanımlamaz, hepsi bu şemadan türetilir.

## Backend ↔ Frontend (opsiyonel — artık aynı repo/image, zorunlu değil)

Frontend backend'e birleştiği için bu adım artık zorunlu değil, ama tip güvenliği
için önerilir. FastAPI her başlattığında `http://localhost:8000/openapi.json`'ı
otomatik üretir. Frontend bunu TypeScript tiplerine çevirebilir:

```bash
cd frontend
npx openapi-typescript http://localhost:8000/openapi.json -o src/api/generated/schema.d.ts
```

Backend'de bir endpoint/model değiştiğinde, isteyen bu komutu tekrar çalıştırır.
Zorunlu adım listesine dahil değil — küçük/stub sayfalarda elle tip yazmak da kabul
edilebilir.

**Tip kontrolü artık gerçekten çalışıyor.** Kök `tsconfig.json` bir "solution"
dosyası (`files: []`) olduğu için `npm run build` içindeki düz `tsc` hiçbir
dosyaya bakmıyordu; build yeşil görünürken 33 tip hatası birikmişti. Script
`tsc -b`'ye çevrildi ve hatalar giderildi. Ayrı çalıştırmak için:

```bash
cd frontend && npm run typecheck
```

## Backend ↔ ai-service

ai-service, backend'in bazı endpoint'lerini (kullanıcı portföyü, hesap bilgisi, işlem
gerçekleştirme) HTTP ile çağırır. Aynı prensip:

```bash
cd ai-service
datamodel-codegen --url http://localhost:8000/openapi.json \
  --output app/backend_client/models.py
```

ai-service, backend'e giden isteklerde bu üretilmiş Pydantic modellerini kullanır.

## Ne zaman regenerate edilir

- Backend'de bir endpoint eklendiğinde/değiştiğinde/silindiğinde
- Bir Pydantic modelinin alanları değiştiğinde (yeni alan, tip değişikliği, zorunlu→opsiyonel)
- Sprint başında ya da PR merge sonrası, düzenli bir alışkanlık olarak

## PR kuralı

Backend'de bir modelin/endpoint'in şeklini değiştiren PR açıklamasına şu not
eklenmeli:

> ⚠️ Breaking change: `/api/investment/portfolio` response şeması değişti.
> Frontend ve ai-service'in regenerate etmesi gerekiyor.

Bu notu görmeyen kimse "neden benim tarafımda tip hatası çıktı" diye şaşırmaz.

## Neden bu yeterli, neden ekstra bir "Contracts repo/paketi" kurmuyoruz

Yedi mikroservisli senaryoda paylaşılan bir DTO paketi/NuGet/PyPI paketi kurmak
mantıklıydı çünkü hiçbir servis diğerinin kodunu göremiyordu. Modüler monolitte
backend zaten tek codebase — asıl "sözleşme" ihtiyacı sadece dışarıya açılan iki
sınırda var, bu da otomatik üretimle elle bakım yükü olmadan çözülüyor. Ekstra bir
paket/versiyonlama katmanı bu ölçekte gereksiz karmaşıklık olurdu.

## MCP sözleşme sürümü: v2.2

MCP tool'larının gövde/yanıt şemaları "MCP Tools Interface Definitions"a karşı
dondurulmuş. Sürüm geçmişi:

| Sürüm | Değişiklik |
|---|---|
| v2.1 | Altı tool: `get_portfolio_positions`, `rag_semantic_market_search`, `calculate_portfolio_risk_metrics`, `prepare_transaction_proposal`, `validate_compliance_rules`, `route_user_request` |
| **v2.2** | **`get_market_data` eklendi.** Mevcut altı tool'un şeması değişmedi. |
| **v2.6** | `get_market_data` → enstrüman başına `volume`. `get_portfolio_positions` → pozisyon başına `sector` ve `market`. Üçü de eklemeli. Varsayılanı olan string parametreler (`valuation_mode`, `base_currency`, `order_type`, `time_in_force`, `lookback`, `jurisdiction`, `strictness`, `locale`, `rebalance_assumption`) artık `null` kabul edip varsayılana düşer. |
| **v2.5** | `prepare_transaction_proposal` artık kimliği belirsiz bir çağıranı (`user_id` yok / boş / `"anonymous"`) **reddeder** — backend `/transactions/stage` 401 döner. Kırıcı değil: geçerli bir `user_id` ile davranış aynı. Eklemeli: `POST /api/auth/refresh`, `POST /api/ai_orchestrator/chat/stream` (SSE). |
| **v2.4** | Frontend yanıtlarına `currency` eklendi (Position, WatchlistItem, TopMoverItem, DividendItem, HeatmapItem, Order, MarketTicker, CandleSeriesOut). `PortfolioAnalysis` → `base_currency`. Portföy widget'ında pozisyon başına `instrument_currency`. Hepsi eklemeli. |
| **v2.3** | `get_portfolio_positions` → `totals.cash_balance` ve `totals.total_value` (eklemeli). `prepare_transaction_proposal` → `source_account_id` artık opsiyonel. |

v2.6 neden gerekti: `volume` her fiyat satırında saklanıyor ama hiçbir uç
nokta vermiyordu, dolayısıyla taramadaki "Günlük ciro" sütunu bazen değil
HER ZAMAN boştu. `sector` ise risk motorunun sektör kırılımını besliyor;
alan taşınmadığı için her portföy `{"UNCLASSIFIED": 1.0}` olarak raporlanıyordu.

`null` toleransı bir üretim hatasından geldi: planlayıcı sıradan bir
"portföyümü göstersene" turunda `valuation_mode: null` gönderdi, çıplak `str`
anotasyonu çağrıyı araç çalışmadan reddetti ve kullanıcıya sanki backend
çökmüş gibi "portföy verilerinize ulaşamadım" denildi. `null` = "tercihim yok"
demektir; varsayılan tam olarak bunun içindir.

v2.5 neden gerekti: süresi dolmuş bir oturum sessizce anonime düşüyor,
orchestrator kullanıcıyı `"anonymous"` olarak adlandırıyor, hesap araması
paylaşılan DEMO hesabına düşüyordu. Öneri, kullanıcının olmayan bir portföye
göre fiyatlanıyor ve `user_id="anonymous"` ile kaydediliyordu; onay adımının
sahiplik denetimi bunu asla eşleştiremediği için düğme kalıcı olarak 404
veriyordu. Sahibi olmayan bir öneri hiçbir işe yaramaz, o yüzden hiç
oluşturulmuyor.

v2.3 neden gerekti: sözleşmede **nakit yoktu**. `totals` yalnızca piyasa
değeri, maliyet, K/Z ve pozisyon sayısı taşıyordu, dolayısıyla "bakiyem ne
kadar" sorusuna ajan ya portföyün piyasa değerini bakiye diye söylüyor ya da
bilgiyi bulamıyordu. `null` "bilinmiyor" demek — sıfır olarak raporlanmaz,
çünkü sıfır bir iddiadır ve yanlış olanıdır.

`source_account_id` aynı sürümde opsiyonele çevrildi: zorunluyken sohbet
kullanıcıdan hiç doğrulanmayan bir hesap kimliği istiyordu ve gelen "1" değeri
kabul edilip hiçbir yerde kullanılmıyordu. Artık backend çağıranın kendi
hesabını çözüyor.

`get_market_data` neden gerekti: altı tool portföy, doküman, risk, işlem
hazırlama ve yönlendirmeyi kapsıyordu; hiçbiri **kullanıcının sahip olmadığı**
bir enstrümanın fiyatını okuyamıyordu. "THYAO kaç lira?" ve "F/K'sı 10'un
altındaki hisseler" soruları bu yüzden "veri bulunamadı" ile dönüyordu.

Backend karşılığı `GET /api/market/instruments`. Eksik temel oran `null` döner
ve öyle sunulur — 0 olarak göstermek, kârı açıklanmamış bir şirketi listenin en
ucuzu yapardı.

## Zorunlu bildirimler nerede görünür

`compliance` modülü bildirim metnini üretir, ama artık **her yanıta**
eklenmiyor. `DISC-GENERAL` yalnızca turda finansal içerik varsa isteniyor: bir
araç çalıştıysa, metinde rakam geçiyorsa ya da kişisel veri/işlem önerisi
varsa. Selamlaşma ve hata mesajları hiçbir finansal iddia taşımadığı için
bildirim de taşımıyor. (`classify_and_route_intent` her turda çalıştığından
"araç çalıştı" sinyalinin dışında tutuldu — aksi halde koşul arka kapıdan
tekrar "her zaman"a dönerdi.)

Metin `ChatResponse.disclosures` alanında **ayrı** taşınıyor ve arayüzde balonun
altında küçük punto dipnot olarak gösteriliyor. Kelimeler değişmedi, yalnızca
yeri değişti: tek satırlık bir cevabın altına yapıştırılan üç cümlelik kalıp,
okuyucuyu bildirimi gerçekten önemli olduğu yerde de atlamaya alıştırıyordu.

## Kritik akış: chatbot işlem onayı

FG-CB-02 (chatbot piyasa işlemi gerçekleştirebilmeli) ve FOG-03 (hassas işlemler için
ek kimlik doğrulama) birlikte şunu gerektiriyor: ai-service bir işlemi *önerir*,
gerçek gerçekleştirme backend'in investment modülünde, kullanıcının frontend'de açık
onayından **sonra** olur. Tek bir endpoint'e "öner ve hemen gerçekleştir" mantığını
gömmeyin.

Akışın iki ucu:

| Adım | Uç nokta | Kim çağırır |
|---|---|---|
| Öneri hazırla | `POST /api/investment/transactions/stage` | `mcp` (servis kimliğiyle) veya tarayıcı (kullanıcı token'ıyla) |
| Onayla | `POST /api/investment/transactions/{proposal_id}/confirm` | **Yalnızca** tarayıcı, kullanıcının kendi tıklamasıyla |

Eski `POST /investment/orders/propose` ve `/orders/confirm` uçları **kaldırıldı**.
Sabit bir yanıt döndüren taslaklardı: sahiplik, süre ve tekillik denetimlerinin
hiçbirini yapmıyorlardı, `confirm` her `order_id` için "onaylandı" diyordu.
Gösterge panelindeki emir modalı da artık yukarıdaki gerçek yolu kullanıyor.

Önerinin **kime ait olduğu** token'dan belirlenir: `stage` çağrısında token
varsa gövdedeki `user_id` onunla eşleşmek zorunda, aksi halde 403. Token yoksa
gövdedeki değer korunur — `mcp` bu uç noktayı servis kimliğiyle çağırır ve kimin
adına çalıştığını gövdede bildirir. Gövdeye koşulsuz güvenmek, herhangi birinin
bir başkasının emir listesinde öneri belirmesine izin verirdi.
