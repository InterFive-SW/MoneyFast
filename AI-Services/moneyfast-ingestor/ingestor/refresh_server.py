"""Tek uçlu, küçük bir HTTP sunucusu: `POST /refresh`.

Neden var: hisse fiyatları artık on beş dakikada bir tazeleniyor. Ekranlar için
bu yeterli, sohbet için değil -- "THYAO kaç TL" sorusuna on beş dakika önceki
fiyatla cevap vermek, kullanıcının işlem kararını verdiği anda yanlış sayı
göstermek demek. Backend, sohbette bir enstrüman adı geçtiğinde burayı çağırır;
bu servis o sembolleri hemen çeker ve her zamanki yoldan geri iter.

Neden BURADA: yfinance'a çıkan tek bileşen bu servis ve veritabanı kredensiyeli
YOK (bkz. docs/DOCKER_NETWORKING.md). Backend'in doğrudan sağlayıcıya çıkması
daha az parça olurdu ama internet erişimini, veritabanı şifresini tutan katmana
taşırdı.

Neden FastAPI değil: tek bir uç nokta için iki bağımlılık (fastapi, uvicorn)
eklemek, bu servisin bilerek kısa tutulan bağımlılık listesine ödenecek bir
bedel değil. Standart kütüphane yeterli.
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

from . import config, sinks
from .sources import yfinance_source

log = logging.getLogger("moneyfast.ingestor.refresh")

#: Tek çağrıda tazelenebilecek azami sembol. Sohbet bir turda bir avuç
#: enstrümandan söz eder; bu uç noktayı toplu çekim için kullanmak, on beş
#: dakikalık turun var olma sebebini ortadan kaldırırdı.
MAX_SYMBOLS = 25


def _authorised(header: str | None) -> bool:
    """Servis anahtarı doğru mu.

    Anahtar tanımsızsa REDDEDİLİR, açılmaz: bir env değişkeni eksik diye
    sessizce herkese açılan bir uç nokta, kimsenin fark etmediği türden bir şey.
    """
    expected = config.service_token()
    return bool(expected) and header == f"Bearer {expected}"


def refresh(symbols: list[str]) -> dict:
    """İstenen sembolleri şimdi çeker ve backend'e iter."""
    wanted = {str(s).strip().upper() for s in symbols if str(s).strip()}
    if not wanted:
        return {"refreshed": 0, "symbols": []}

    with httpx.Client() as client:
        products = [
            p for p in sinks.fetch_products(client)
            if str(p.get("symbol", "")).upper() in wanted
        ]
        if not products:
            return {"refreshed": 0, "symbols": []}

        quotes = yfinance_source.fetch_quotes(products)
        result = sinks.push_market_data(client, quotes, []) or {}

    log.info("refreshed %d/%d requested symbol(s)", len(quotes), len(wanted))
    return {
        "refreshed": result.get("quotes_written", len(quotes)),
        "symbols": sorted(str(q.get("symbol", "")) for q in quotes),
    }


class _Handler(BaseHTTPRequestHandler):
    server_version = "MoneyFastIngestor/1.0"

    def _reply(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib arayüzü
        if self.path == "/health":
            self._reply(200, {"status": "ok"})
        else:
            self._reply(404, {"detail": "Not found."})

    def do_POST(self) -> None:  # noqa: N802 - stdlib arayüzü
        if self.path != "/refresh":
            self._reply(404, {"detail": "Not found."})
            return
        if not _authorised(self.headers.get("Authorization")):
            self._reply(401, {"detail": "Invalid service credentials."})
            return

        try:
            length = int(self.headers.get("content-length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
            symbols = payload.get("symbols") or []
            if not isinstance(symbols, list):
                raise ValueError("symbols must be a list")
        except (ValueError, json.JSONDecodeError) as exc:
            self._reply(400, {"detail": f"Bad request: {exc}"})
            return

        if len(symbols) > MAX_SYMBOLS:
            self._reply(400, {"detail": f"En fazla {MAX_SYMBOLS} sembol."})
            return

        try:
            self._reply(200, refresh(symbols))
        except Exception as exc:  # sağlayıcı hatası turu düşürmemeli
            log.warning("refresh failed: %s", exc)
            self._reply(502, {"detail": "Sağlayıcıdan fiyat alınamadı."})

    def log_message(self, fmt: str, *args) -> None:
        """stderr'e değil, servisin kendi log'una."""
        log.debug(fmt, *args)


def serve_in_background(port: int | None = None) -> ThreadingHTTPServer:
    """Sunucuyu arka planda başlatır ve döner.

    Daemon iş parçacığı: zamanlayıcı ana iş parçacığında bloklamaya devam
    ediyor ve süreç kapanırken sunucu onu bekletmiyor.
    """
    # `port is None`, `port or ...` DEĞİL: 0 geçerli bir değer -- "boş bir port
    # seç" demek ve çekirdek onu öyle anlıyor. `or` ile yazıldığında 0 "değer
    # verilmedi" sayılıp varsayılana düşüyordu.
    chosen = config.refresh_port() if port is None else port
    server = ThreadingHTTPServer(("0.0.0.0", chosen), _Handler)
    thread = threading.Thread(
        target=server.serve_forever, name="refresh-server", daemon=True
    )
    thread.start()
    log.info("refresh endpoint listening on :%d", server.server_address[1])
    return server
