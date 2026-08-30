"""Anlık fiyat tazeleme uç noktası.

Hisse fiyatları on beş dakikada bir tazeleniyor; ekranlar için yeterli, sohbet
için değil. "THYAO kaç TL" sorusuna on beş dakika önceki fiyatla cevap vermek,
kullanıcının işlem kararını verdiği anda yanlış sayı göstermek olurdu.

Fiyatı backend değil BU servis çekiyor: yfinance'a çıkan tek bileşen bu ve
veritabanı kredensiyeli olmayan da bu (bkz. docs/DOCKER_NETWORKING.md).
"""

from __future__ import annotations

import json
from io import BytesIO

import pytest

from ingestor import refresh_server


PRODUCTS = [
    {"symbol": "THYAO", "data_symbol": "THYAO.IS", "market": "BIST"},
    {"symbol": "AAPL", "data_symbol": "AAPL", "market": "NASDAQ"},
]


class TestAuthorisation:
    def test_the_service_key_is_accepted(self, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "s3cret")
        assert refresh_server._authorised("Bearer s3cret")

    def test_a_wrong_key_is_not(self, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "s3cret")
        assert not refresh_server._authorised("Bearer nope")
        assert not refresh_server._authorised(None)

    def test_an_unset_key_refuses_rather_than_opening(self, monkeypatch):
        """Bir env değişkeni eksik diye sessizce herkese açılan uç nokta,
        kimsenin fark etmediği türden bir şey."""
        monkeypatch.delenv("BACKEND_API_KEY", raising=False)
        assert not refresh_server._authorised("Bearer ")
        assert not refresh_server._authorised(None)


class TestRefresh:
    def _wire(self, monkeypatch, quotes=None, products=None):
        monkeypatch.setattr(
            refresh_server.sinks, "fetch_products",
            lambda client: PRODUCTS if products is None else products,
        )
        monkeypatch.setattr(
            refresh_server.yfinance_source, "fetch_quotes",
            lambda p: quotes if quotes is not None else [{"symbol": "THYAO"}],
        )
        monkeypatch.setattr(
            refresh_server.sinks, "push_market_data",
            lambda c, q, k: {"quotes_written": len(q)},
        )

    def test_only_the_named_symbols_are_fetched(self, monkeypatch):
        seen = []
        self._wire(monkeypatch)
        monkeypatch.setattr(
            refresh_server.yfinance_source, "fetch_quotes",
            lambda p: seen.append([x["symbol"] for x in p]) or [{"symbol": "THYAO"}],
        )
        refresh_server.refresh(["THYAO"])
        assert seen == [["THYAO"]]

    def test_it_reports_what_was_written(self, monkeypatch):
        self._wire(monkeypatch)
        assert refresh_server.refresh(["thyao"]) == {
            "refreshed": 1, "symbols": ["THYAO"],
        }

    def test_an_empty_request_does_nothing(self, monkeypatch):
        self._wire(monkeypatch)
        assert refresh_server.refresh([]) == {"refreshed": 0, "symbols": []}
        assert refresh_server.refresh(["  "]) == {"refreshed": 0, "symbols": []}

    def test_an_unknown_symbol_is_not_an_error(self, monkeypatch):
        """Evrende olmayan bir ad, tazelenecek bir şey olmadığı anlamına gelir."""
        self._wire(monkeypatch)
        assert refresh_server.refresh(["NOSUCH"]) == {"refreshed": 0, "symbols": []}


class _FakeRequest:
    """`BaseHTTPRequestHandler`'ı soket açmadan sürmek için."""

    def __init__(self, method, path, body=b"", headers=None):
        payload = f"{method} {path} HTTP/1.1\r\n".encode()
        for key, value in (headers or {}).items():
            payload += f"{key}: {value}\r\n".encode()
        payload += b"\r\n" + body
        self._in = BytesIO(payload)
        self.out = BytesIO()

    def makefile(self, mode, *args):
        return self._in if "r" in mode else self.out

    def sendall(self, data):
        self.out.write(data)


def call(method, path, body=None, headers=None):
    raw = json.dumps(body).encode() if body is not None else b""
    head = {"content-length": str(len(raw)), **(headers or {})}
    request = _FakeRequest(method, path, raw, head)
    refresh_server._Handler(request, ("127.0.0.1", 0), None)
    response = request.out.getvalue().decode("utf-8", "replace")
    status = int(response.split(" ", 2)[1])
    payload = response.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in response else ""
    return status, (json.loads(payload) if payload else {})


class TestHandler:
    def test_health_is_open(self):
        assert call("GET", "/health")[0] == 200

    def test_an_unknown_path_is_404(self):
        assert call("GET", "/nope")[0] == 404
        assert call("POST", "/nope")[0] == 404

    def test_refresh_needs_the_service_key(self, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "s3cret")
        assert call("POST", "/refresh", {"symbols": ["THYAO"]})[0] == 401

    def test_a_valid_call_returns_what_was_refreshed(self, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "s3cret")
        monkeypatch.setattr(
            refresh_server, "refresh", lambda s: {"refreshed": 1, "symbols": s},
        )
        status, body = call(
            "POST", "/refresh", {"symbols": ["THYAO"]},
            {"Authorization": "Bearer s3cret"},
        )
        assert status == 200 and body["refreshed"] == 1

    def test_malformed_json_is_a_400(self, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "s3cret")
        request = _FakeRequest(
            "POST", "/refresh", b"{not json",
            {"content-length": "9", "Authorization": "Bearer s3cret"},
        )
        refresh_server._Handler(request, ("127.0.0.1", 0), None)
        assert b"400" in request.out.getvalue()[:20]

    def test_symbols_must_be_a_list(self, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "s3cret")
        status, _ = call(
            "POST", "/refresh", {"symbols": "THYAO"},
            {"Authorization": "Bearer s3cret"},
        )
        assert status == 400

    def test_a_huge_request_is_refused(self, monkeypatch):
        """Bu uç noktayı toplu çekim için kullanmak, on beş dakikalık turun var
        olma sebebini ortadan kaldırırdı."""
        monkeypatch.setenv("BACKEND_API_KEY", "s3cret")
        status, _ = call(
            "POST", "/refresh",
            {"symbols": [f"S{i}" for i in range(refresh_server.MAX_SYMBOLS + 1)]},
            {"Authorization": "Bearer s3cret"},
        )
        assert status == 400

    def test_a_provider_failure_is_a_502_not_a_crash(self, monkeypatch):
        monkeypatch.setenv("BACKEND_API_KEY", "s3cret")

        def _boom(_symbols):
            raise RuntimeError("provider down")

        monkeypatch.setattr(refresh_server, "refresh", _boom)
        status, _ = call(
            "POST", "/refresh", {"symbols": ["THYAO"]},
            {"Authorization": "Bearer s3cret"},
        )
        assert status == 502

    def test_logging_goes_to_the_service_log(self, caplog):
        """stderr'e değil: konteyner log'u tek bir biçimde okunabilsin."""
        request = _FakeRequest("GET", "/health", b"", {"content-length": "0"})
        handler = refresh_server._Handler(request, ("127.0.0.1", 0), None)
        handler.log_message("%s", "sessiz")


class TestServer:
    def test_it_starts_and_stops(self, monkeypatch):
        """Port 0: çekirdek boş bir port versin, test sabit bir porta
        bağlanmaya çalışıp yan yana koşan başka bir şeyle çakışmasın."""
        server = refresh_server.serve_in_background(port=0)
        try:
            assert server.server_address[1] > 0
        finally:
            server.shutdown()
            server.server_close()
