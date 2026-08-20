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

`get_market_data` neden gerekti: altı tool portföy, doküman, risk, işlem
hazırlama ve yönlendirmeyi kapsıyordu; hiçbiri **kullanıcının sahip olmadığı**
bir enstrümanın fiyatını okuyamıyordu. "THYAO kaç lira?" ve "F/K'sı 10'un
altındaki hisseler" soruları bu yüzden "veri bulunamadı" ile dönüyordu.

Backend karşılığı `GET /api/market/instruments`. Eksik temel oran `null` döner
ve öyle sunulur — 0 olarak göstermek, kârı açıklanmamış bir şirketi listenin en
ucuzu yapardı.

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
