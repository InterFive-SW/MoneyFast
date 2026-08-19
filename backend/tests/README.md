# Backend Unit Testleri

Bu klasör, backend'in %100 satır + dal (branch) coverage'lı, tamamen izole
unit test takımını içerir. Gerçek bir Postgres bağlantısı **gerekmez** ve
gerçek bir ağ isteği **atmaz** — hem geliştirme makinesinde hem CI'da
(Docker/Postgres kapalıyken bile) aynı şekilde çalışır.

## Son doğrulanan sonuç (2026-08-19)

```
487 statement, 36 branch — %100 satır + %100 dal coverage
98 test, hepsi geçti, ~4 saniyede tamamlandı
```

Postgres tamamen kapalıyken (`docker compose down`) da aynı sonuçla
doğrulandı — suite'in gerçekten izole olduğunun kanıtı, varsayım değil.
Bu sayılar test eklendikçe değişecek; güncel referans her zaman `pytest`
komutunun kendi çıktısıdır, bu blok sadece son bilinen durumun kaydıdır.

## Çalıştırma

```bash
cd backend
pip install -r requirements.txt -r requirements-test.txt   # ilk kurulum
pytest                                                       # testler + coverage
```

Veya `Makefile` üzerinden:

```bash
make install-test   # bağımlılıkları kur
make test           # %100 gate ile testleri çalıştır
make coverage-html  # htmlcov/index.html üret
make help           # tüm hedefleri listele
```

`pytest.ini`'deki `--cov-fail-under=100` sayesinde coverage %100'ün altında
kalırsa komut **hata koduyla biter** — yani bu takım "yeşil ama eksik"
görünmez, ya tam geçer ya da açıkça başarısız olur.

## İzolasyon ilkeleri

- **DB yok:** `tests/conftest.py`, herhangi bir `app.*` modülü import
  edilmeden önce `DATABASE_URL`'i in-memory SQLite'a ayarlıyor. Router'ların
  hiçbiri gerçek DB sorgusu yapmıyor (`auth/service.py` hariç — o da mock
  `Session` ile ayrı test ediliyor).
- **Ağ yok:** `block_network` (autouse fixture) gerçek bir soket açan
  testi patlatır. Backend'deki tek dış HTTP çağrısı (`ai_orchestrator`
  modülünün AI servisine gidişi) bu yüzden her testte mock'lanmak zorunda.
- **Yavaş yan etkiler hızlandırılmış:** `no_sleep` fixture'ı
  `ai_assistant`'ın `asyncio.sleep(1.5)`'ini no-op'a çeviriyor;
  `password_hash_factory` bcrypt hash'lerini (~250ms) testler arası
  yeniden kullanıyor.

## Kapsam

| Alan | Yaklaşım |
|---|---|
| `core/` (config, database, security) | Doğrudan birim testleri |
| `auth/` | Router (HTTP sözleşmesi) + service (mock DB) + schemas (validator) + models (gerçek in-memory SQLite ile default değerler) ayrı ayrı |
| `investment/`, `market/` | **Sözleşme testi**: mock endpoint'ler tek satırlık gövdeler olduğu için "200 dönüyor mu + yanıt şemaya uyuyor mu" testi hem %100 verir hem DB entegrasyonundan sonra da değerini korur — endpoint gövdesi mock'tan gerçek sorguya dönse bile şema aynı kaldığı sürece bu testler geçmeye devam eder |
| `ai_assistant/` | Kural tabanlı if/elif zincirinin her dalı ve iç branch'leri (miktar çıkarma, al/sat ayrımı) |
| `ai_orchestrator/` | `httpx` çağrısının 4 senaryosu: başarı, bağlantı reddi, zaman aşımı, orchestrator hata durumu |
| `banking/`, `notification/`, `analytics/` | Şu an sadece health endpoint'i var (models/service boş) |
| `main.py` | Router auto-discovery'nin 4 dalı (monkeypatch ile) + SPA fallback'in 3 dalı (`Path.exists` patch + `importlib.reload`, çünkü `backend/frontend/dist` lokalde yok) |

## Konvansiyon

AI ekibinin `AI-Services/moneyfast-orchestrator/mcp-server/tests/`
altındaki test takımından esinlenildi (çift %100 gate, `pytest-mock`'un
`mocker` fixture'ı, davranış anlatan İngilizce test adları, `block_network`
fikri) — ama bu iki takım birbirinden **tamamen bağımsız**: ayrı
`pytest.ini`, ayrı `conftest.py`, ayrı kök. Biri diğerine dokunmadan
çalışır.

## Bilinen sınırlama

`investment`/`market`/`auth` router'larının büyük kısmı hâlâ mock veri
döndürüyor (DB henüz bağlı değil). Bu testler o mock davranışını bir
sözleşme olarak sabitliyor; gerçek DB sorguları devreye alındığında
(`auth/service.py`'nin `router.py`'den çağrılması gibi) ilgili testler
güncellenmeli — ama HTTP sözleşmesi (durum kodları, response şekli) aynı
kalmalı.
