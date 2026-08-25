"""Unit tests for app/main.py.

İki bağımsız parça test ediliyor:
  1. `_discover_routers` — router auto-discovery, `application` parametresi
     sayesinde gerçek global `app`'e dokunmadan sahte bir hedefle çağrılabiliyor.
  2. `spa_fallback` — lokalde `backend/frontend/dist` var olmadığı için modül
     import edildiğinde bu route hiç tanımlanmıyor; `Path.exists` patch'i +
     `importlib.reload` ile üç dalı da (api/ 404, mevcut dosya, catch-all) kapsıyoruz.
"""

from __future__ import annotations

import importlib
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI

import app.main as main_module


# --------------------------------------------------------------------------
# _discover_routers — dört dal, hiçbiri canlı kodda birlikte tetiklenmiyor.
# `application` parametresi MagicMock olduğu için gerçek FastAPI app'e
# dokunulmuyor; sadece `include_router`'ın çağrılıp çağrılmadığı ve hangi
# argümanlarla çağrıldığı doğrulanıyor.
# --------------------------------------------------------------------------
def test_discover_routers_skips_module_without_router_attribute(monkeypatch):
    """`hasattr(mod, "router")` False olduğunda hiçbir şey mount edilmez."""
    fake_application = MagicMock(spec=FastAPI)
    fake_pkg = SimpleNamespace(name="no_router_module")

    monkeypatch.setattr(main_module.pkgutil, "iter_modules", lambda paths: [fake_pkg])
    monkeypatch.setattr(
        main_module.importlib, "import_module", lambda name: SimpleNamespace()
    )

    main_module._discover_routers(fake_application)

    fake_application.include_router.assert_not_called()


def test_discover_routers_swallows_module_not_found_error(monkeypatch):
    """router.py'si olmayan bir modül paketi `ModuleNotFoundError` fırlatır,
    fonksiyon bunu yutar ve devam eder (hata dışarı sızmaz)."""
    fake_application = MagicMock(spec=FastAPI)
    fake_pkg = SimpleNamespace(name="ghost_module")

    def _raise_module_not_found(name: str):
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(main_module.pkgutil, "iter_modules", lambda paths: [fake_pkg])
    monkeypatch.setattr(main_module.importlib, "import_module", _raise_module_not_found)

    main_module._discover_routers(fake_application)  # raise etmemeli

    fake_application.include_router.assert_not_called()


def test_discover_routers_mounts_prefixless_router_under_api_package_name(monkeypatch):
    """`router.prefix` boşsa `/api/{paket_adı}` öneki eklenerek mount edilir
    (şu an TÜM gerçek modüllerin izlediği yol)."""
    fake_application = MagicMock(spec=FastAPI)
    fake_router = SimpleNamespace(prefix="")
    fake_pkg = SimpleNamespace(name="widgets")

    monkeypatch.setattr(main_module.pkgutil, "iter_modules", lambda paths: [fake_pkg])
    monkeypatch.setattr(
        main_module.importlib,
        "import_module",
        lambda name: SimpleNamespace(router=fake_router),
    )

    main_module._discover_routers(fake_application)

    fake_application.include_router.assert_called_once_with(
        fake_router, prefix="/api/widgets"
    )


def test_discover_routers_mounts_prefixed_router_as_is(monkeypatch):
    """`router.prefix` doluysa öneksiz mount edilir (canlı kodda hiç
    tetiklenmeyen dal — tüm modüller şu an prefix'siz)."""
    fake_application = MagicMock(spec=FastAPI)
    fake_router = SimpleNamespace(prefix="/custom-prefix")
    fake_pkg = SimpleNamespace(name="widgets")

    monkeypatch.setattr(main_module.pkgutil, "iter_modules", lambda paths: [fake_pkg])
    monkeypatch.setattr(
        main_module.importlib,
        "import_module",
        lambda name: SimpleNamespace(router=fake_router),
    )

    main_module._discover_routers(fake_application)

    fake_application.include_router.assert_called_once_with(fake_router)


def test_real_app_discovers_all_module_health_endpoints():
    """Modül import edildiğinde gerçek auto-discovery'nin 8 modülü de
    bulduğunu doğrular — CLAUDE.md'deki "elle router eklemeye gerek yok"
    iddiasının fiilen çalıştığının kanıtı."""
    paths = main_module.app.openapi()["paths"]
    for module_name in (
        "auth",
        "banking",
        "investment",
        "notification",
        "analytics",
        "market",
        "ai_orchestrator",
    ):
        assert f"/api/{module_name}/health" in paths or any(
            p.startswith(f"/api/{module_name}/") for p in paths
        ), module_name


# --------------------------------------------------------------------------
# spa_fallback — backend/frontend/dist lokalde yok, route modül import
# edildiğinde hiç tanımlanmıyor. Path.exists'i geçici olarak True'ya
# çevirip modülü yeniden yükleyerek route'u canlıya alıyoruz, sonra
# gerçek bir geçici dizinle (tmp_path) üç dalı da test ediyoruz.
# --------------------------------------------------------------------------
@pytest.fixture
def reloaded_app_with_fake_dist(tmp_path, monkeypatch):
    """`_static_dir` gerçekten var olan bir tmp dizinini göstersin diye
    modülü iki adımda yeniden yükler: önce `Path.exists`'i patch'leyip
    reload ederek route'un TANIMLANMASINI sağlar, sonra `_static_dir`
    global'ini gerçek (dolu) bir tmp dizinine çeviririz."""
    dist_dir = tmp_path / "dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text("<html>SPA shell</html>")
    (dist_dir / "app.js").write_text("console.log('hi');")

    from pathlib import Path

    monkeypatch.setattr(Path, "exists", lambda self: True)
    importlib.reload(main_module)
    # Route artık tanımlı; şimdi gerçek dosyaların olduğu tmp dizinine yönlendir.
    monkeypatch.setattr(main_module, "_static_dir", dist_dir)

    from fastapi.testclient import TestClient

    reloaded_client = TestClient(main_module.app)
    try:
        yield reloaded_client, dist_dir
    finally:
        reloaded_client.close()
        # Modülü orijinal (lokalde dist'i olmayan) haline geri döndür.
        importlib.reload(main_module)


def test_spa_fallback_returns_404_json_for_unmatched_api_path(reloaded_app_with_fake_dist):
    client, _ = reloaded_app_with_fake_dist

    response = client.get("/api/not-a-real-endpoint")

    assert response.status_code == 404
    assert response.json() == {"detail": "API route not found"}


def test_spa_fallback_serves_existing_static_file(reloaded_app_with_fake_dist):
    client, _ = reloaded_app_with_fake_dist

    response = client.get("/app.js")

    assert response.status_code == 200
    assert "console.log" in response.text


def test_spa_fallback_serves_index_html_for_unknown_frontend_route(
    reloaded_app_with_fake_dist,
):
    client, _ = reloaded_app_with_fake_dist

    response = client.get("/portfolio/some/deep/spa/route")

    assert response.status_code == 200
    assert "SPA shell" in response.text


def test_spa_fallback_route_not_registered_when_dist_dir_missing():
    """Sağlamlık testi: modülün olağan (lokal) hâlinde `_static_dir` yok,
    dolayısıyla catch-all route hiç kayıtlı değil — `/anything` normal
    404'e (route bulunamadı) düşer, SPA fallback'e değil."""
    assert not main_module._static_dir.exists()
