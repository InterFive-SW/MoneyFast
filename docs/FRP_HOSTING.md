# FRP ile Yayına Açmak — Uygulamayı Oracle Üzerinden Erişilebilir Kılmak

Bu doküman, geliştirme makinesinde `docker compose up` ile çalışan MoneyFast'i,
Oracle Cloud'daki ücretsiz sunucuda duran bir **frps** üzerinden dışarıya
açmayı anlatır. Amaç: demo linkini paylaşabilmek, ve tünel çalışmadığında
nereye bakılacağını bilmek.

`frp` (fast reverse proxy) iki parçadır:

- **`frps`** — Oracle'daki sunucuda çalışır, public IP'si olan taraf.
- **`frpc`** — bizim makinemizde çalışır, `frps`'e **dışarı doğru** bağlanır.

Bağlantıyı istemci kurduğu için bizim tarafımızda **hiçbir port açılmaz**:
modem ayarı, port yönlendirme, statik IP gerekmez. CGNAT arkasında da çalışır.

## 1. Neden bu uygulamada kolay: tek port

Tünellemeyi genelde zorlaştıran dört şey var ve dördü de burada zaten doğru:

| Konu | Durum |
|---|---|
| Host'a açılan port | **Bir tane.** `docker-compose.yml`'de sadece `backend` `8000:8000` yayınlıyor (bkz. `web-ingress` yorumu) |
| Frontend | Backend'in kendisi serve ediyor (`StaticFiles`), ayrıca açılacak ikinci bir servis yok |
| API adresi | `client.ts`'te `baseUrl = '/api'` — **göreli**. Ne `VITE_API_URL` var ne de gömülü `localhost:8000` |
| Oturum | JWT `localStorage`'da, cookie değil — origin değişince `SameSite`/`Domain` sorunu çıkmaz |

Son satır önemli: cookie tabanlı oturum, hostname değişir değişmez bozulur.
Bearer token bunu umursamaz.

Frontend backend ile **aynı origin'den** servis edildiği için tünelin arkasında
tarayıcı hiçbir isteği cross-origin saymaz — yani `main.py`'deki
`allow_origins=["http://localhost:5173", ...]` listesi sorun çıkarmaz,
değiştirilmesi de gerekmez. Sadece Vite dev sunucusu (`npm run dev`) için var.

Sonuç: **frp'nin tek bir TCP portunu taşıması yeterli.**

## 2. Oracle tarafı (bir kez)

### 2.1 frps kurulumu

```bash
FRP_VERSION=0.61.0
curl -LO https://github.com/fatedier/frp/releases/download/v${FRP_VERSION}/frp_${FRP_VERSION}_linux_amd64.tar.gz
tar -xzf frp_${FRP_VERSION}_linux_amd64.tar.gz
sudo install -m 755 frp_${FRP_VERSION}_linux_amd64/frps /usr/local/bin/frps
sudo mkdir -p /etc/frp
```

> Oracle'ın ücretsiz ARM (Ampere) makinesini kullanıyorsanız `linux_amd64`
> yerine **`linux_arm64`** indirin. Yanlış mimari, çalıştırınca
> `cannot execute binary file` verir.

`/etc/frp/frps.toml`:

```toml
bindPort = 7000

auth.method = "token"
auth.token = "<uzun-rastgele-token>"

# Sadece izin verilen portlar tünellenebilir. Bunu yazmazsanız bağlanan
# herkes istediği portu açabilir.
allowPorts = [{ start = 8000, end = 8010 }]

log.to = "/var/log/frps.log"
log.level = "info"
```

Token'ı `openssl rand -hex 32` ile üretin. Bu token, tünele kimin
bağlanabileceğini belirleyen tek şey.

### 2.2 systemd — tarayıcıya gerek yok

**Sık sorulan soru: Oracle'ı tarayıcıda açık tutmak gerekiyor mu? Hayır.**
`frps` bir servis olarak çalışır; SSH oturumunuz kapansa da, siz uyusanız da,
makine yeniden başlasa da ayaktadır.

`/etc/systemd/system/frps.service`:

```ini
[Unit]
Description=frp server
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/frps -c /etc/frp/frps.toml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now frps
sudo systemctl status frps
```

### 2.3 İki ayrı güvenlik duvarı — asıl tuzak burada

Tarayıcıya **yalnızca** bu adım için gireceksiniz, o da bir kez.

Oracle'da port açmak **iki yerde** yapılır ve biri diğerini kapsamaz:

**a) VCN Security List / NSG** — Oracle Console'dan:
`Networking → Virtual Cloud Networks → <VCN> → Security Lists → Default`
→ *Add Ingress Rules*:

| Source CIDR | Protocol | Destination Port | Ne için |
|---|---|---|---|
| `0.0.0.0/0` | TCP | `7000` | frpc → frps kontrol bağlantısı |
| `0.0.0.0/0` | TCP | `8000` | Uygulamanın yayınlandığı port (`remotePort`) |

**b) Makinenin kendi iptables'ı.** Oracle'ın Ubuntu ve Oracle Linux
imajları, image'ın içinde kısıtlayıcı kurallarla gelir ve **Security List
değişikliği bunlara dokunmaz.** Console'dan portu açarsınız, hâlâ
çalışmaz, ve hata frp'deymiş gibi görünür. Neredeyse herkes burada takılır.

Ubuntu:

```bash
sudo iptables -I INPUT 6 -p tcp --dport 7000 -j ACCEPT
sudo iptables -I INPUT 6 -p tcp --dport 8000 -j ACCEPT
sudo netfilter-persistent save
```

Oracle Linux:

```bash
sudo firewall-cmd --permanent --add-port=7000/tcp
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

## 3. Yerel taraf

### 3.1 Sırlar `.env`'de, config commit'lenir

`frpc.toml`'a token'ı doğrudan yazmayın: `.gitignore` yalnızca `*.env`
kalıbını tutuyor, `infra/frpc.toml` commit'lenir ve token repo'ya girer.

frp, config dosyasında ortam değişkeni okuyabiliyor. Bu yüzden dosyanın
kendisi commit'lenir, değerler `infra/.env`'den gelir — projedeki
`BACKEND_API_KEY` ile aynı düzen.

`infra/.env` (ve aynı satırlar `infra/.env.example`'a **değersiz** olarak):

```
FRP_SERVER_ADDR=<oracle-public-ip>
FRP_SERVER_PORT=7000
FRP_TOKEN=<frps.toml'daki token>
FRP_REMOTE_PORT=8000
```

### 3.2 `infra/frpc.toml`

```toml
serverAddr = "{{ .Envs.FRP_SERVER_ADDR }}"
serverPort = {{ .Envs.FRP_SERVER_PORT }}

auth.method = "token"
auth.token = "{{ .Envs.FRP_TOKEN }}"

# Kontrol bağlantısını şifreler. Uygulama trafiği hâlâ düz HTTP;
# TLS için bkz. bölüm 7.
transport.tls.enable = true

[[proxies]]
name = "moneyfast"
type = "tcp"
localIP = "backend"
localPort = 8000
remotePort = {{ .Envs.FRP_REMOTE_PORT }}
```

**`type = "tcp"` — `http` değil.** Gerekçe bölüm 6'da; sessizce bozulan tek
şey bu.

**`localIP = "backend"`**, servis adı. `docker-compose.yml`'de container'lar
birbirine servis adıyla ulaşır (bkz. `DOCKER_NETWORKING.md`), dolayısıyla
`network_mode: host`'a da `host.docker.internal`'a da gerek yok.

### 3.3 `docker-compose.yml`'ye eklenecek

Servis:

```yaml
  frpc:
    image: snowdreamtech/frpc:latest
    # Profil olmadan başlamaz: `docker compose up --build` yapan bir ekip
    # arkadaşı tüneli hiç görmez.
    profiles: ["tunnel"]
    env_file:
      - .env
    volumes:
      - ./frpc.toml:/etc/frp/frpc.toml:ro
    networks:
      # backend:8000'e ulaşmak için.
      - moneyfast-net
      # Oracle'a çıkmak için. moneyfast-net `internal: true`, yani
      # oradan dışarı çıkılamaz.
      - tunnel-egress
    depends_on:
      - backend
    restart: unless-stopped
```

Ağ (`networks:` bloğunun sonuna):

```yaml
  # Tünelin dış bağlantısı. ai-egress/data-egress ile aynı mantık:
  # dışarı çıkan her servisin çıkma sebebi ayrı ayrı yazılı.
  tunnel-egress:
    driver: bridge
```

`frpc`'yi `web-ingress`'e **bağlamayın**. O ağın compose içindeki yorumu
"bilerek tek servis tutuyor" diyor; tünelin ihtiyacı zaten farklı (biri
içeri, diğeri dışarı).

### 3.4 Çalıştırma

```bash
cd infra && docker compose --profile tunnel up -d
```

Tünelsiz normal geliştirme hiç değişmez:

```bash
cd infra && docker compose up --build
```

## 4. Doğrulama

Sırayla, ilk başarısız olan adım sorunun yerini söyler.

**a) frps ayakta mı:**

```bash
sudo systemctl is-active frps
```

**b) frpc bağlandı mı** — logda `start proxy success` görünmeli:

```bash
docker compose --profile tunnel logs frpc | tail -20
```

**c) Sayfa geliyor mu:**

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://<oracle-ip>:8000/
```

**d) SSE akıyor mu — bu adımı atlamayın.** Birkaç saniye içinde `data:`
satırları düşmeye başlamalı; boş kalıyorsa bkz. bölüm 6:

```bash
curl -N --max-time 10 http://<oracle-ip>:8000/api/market/stream
```

**e) Tarayıcıda** `http://<oracle-ip>:8000` — giriş yapın, Piyasalar'ı açın
ve fiyat şeridinin **hareket ettiğini** görün.

## 5. Sorun giderme

| Belirti | Sebep |
|---|---|
| `frpc` sürekli yeniden bağlanıyor, `dial tcp ... i/o timeout` | 7000 portu Security List'te veya **iptables'ta** kapalı (bölüm 2.3 — çoğu zaman ikincisi) |
| `authorization failed` / `token in login doesn't match` | `infra/.env`'deki `FRP_TOKEN` ile `frps.toml`'daki token farklı |
| `port not allowed` | `remotePort`, `frps.toml`'daki `allowPorts` aralığının dışında |
| `frpc` bağlanıyor ama sayfa açılmıyor | `remotePort` (8000) Oracle'da açılmamış; kontrol portu ayrı, veri portu ayrı |
| `connection refused` — frpc → backend | Backend ayakta değil, ya da `localIP` yanlış (`localhost` yazılmış olabilir; `backend` olmalı) |
| Sayfa açılıyor, fiyatlar donuk / sohbet geç ve toplu geliyor | SSE tamponlanıyor — bölüm 6 |
| `cannot execute binary file` | ARM makinede amd64 binary |

## 6. SSE: sessizce bozulan tek şey

Uygulamada iki adet Server-Sent Events akışı var:

- `/api/market/stream` — canlı fiyat (`useMarketStream.ts`)
- `/api/ai_orchestrator/chat/stream` — sohbet ilerleme olayları

`type = "tcp"` bir bayt borusudur, tamponlayamaz. Ama araya HTTP seviyesinde
bir proxy girerse (frp'nin `type = "http"`'si, ya da Oracle'a koyacağınız
nginx) yanıt tamponlanabilir ve iki akış da durur.

Bunun kötü tarafı **sessiz olması**: iki taraf da geri düşüş (fallback)
yapacak şekilde yazıldı — fiyat akışı 10 saniyelik yoklamaya, sohbet ise
tamponlu `/chat` uç noktasına düşer. Yani uygulama çalışmaya devam eder,
sadece ölü hisseder: fiyatlar donar, sohbet bir süre bekleyip cevabı tek
seferde yazar. Frontend'de aranırsa günler alır.

nginx koyacaksanız:

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_buffering off;      # ← SSE için zorunlu
    proxy_read_timeout 3600s;
}
```

Alan adı istiyorsanız frp'nin `vhostHTTPPort` + `customDomains` yolu da
kullanılabilir; ama o durumda yayına almadan önce yukarıdaki (d) adımını
mutlaka çalıştırın.

## 7. Yayına açmadan önce

- **Trafik düz HTTP.** `http://ip:8000` üzerinden JWT'ler açık metin
  gidiyor. Demo için kabul edilebilir; kalıcı olacaksa Oracle'a Caddy
  koyup TLS sonlandırın (`proxy_buffering off` karşılığıyla birlikte).
- **Seed hesapları internete açılıyor.** `seeds/` içindeki demo
  kullanıcıları (`admin` dahil) sabit paroluyla yükleniyor. Yayına
  almadan önce parolaları değiştirin.
- **Veri sentetik**, ama uygulama gerçek gibi davranıyor: para hareketi,
  bakiye, işlem geçmişi. Linki paylaşırken bunun bir demo olduğu
  söylenmeli.
- `infra/.env` commit'lenmiyor (`.gitignore`'da `*.env`). `FRP_TOKEN`'ı
  ekip arkadaşlarına repo üzerinden değil, ayrı kanaldan verin.
