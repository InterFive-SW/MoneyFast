import importlib
import pkgutil
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="MoneyFast API",
    description="Modüler monolit kişisel finans danışmanı backend'i",
    version="0.1.0",
)

"""
CORS (Cross-Origin Resource Sharing) Yapılandırması:
Geliştirme ortamında çalışan frontend uygulamalarının (örn. Vite: 5173, Create React App: 3000)
backend API'sine kısıtlamaya takılmadan, güvenli bir şekilde erişebilmesini sağlar.
"""
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _discover_routers(application: FastAPI) -> None:
    modules_dir = Path(__file__).parent / "modules"
    for pkg in pkgutil.iter_modules([str(modules_dir)]):
        try:
            mod = importlib.import_module(f"app.modules.{pkg.name}.router")
            if hasattr(mod, "router"):
                if not mod.router.prefix:
                    application.include_router(mod.router, prefix=f"/api/{pkg.name}")
                else:
                    application.include_router(mod.router)
        except ModuleNotFoundError:
            pass


_discover_routers(app)

_static_dir = Path(__file__).parent.parent / "frontend" / "dist"

if _static_dir.exists():
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        # 1. API İstekleri İçin İzolasyon
        # Backend'de karşılığı olmayan /api/ ile başlayan istekler SPA'ya (index.html)
        # yönlendirilmemeli, doğrudan JSON formatında 404 hatası döndürülmelidir.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")
            
        # 2. Statik Dosya Kontrolü
        # İstek yapılan dosya gerçekten mevcutsa o dosyayı döndür
        file_path = _static_dir / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
            
        # 3. Catch-All SPA Yönlendirmesi
        # Diğer tüm isteklerde (frontend rotaları) index.html döndür
        return FileResponse(str(_static_dir / "index.html"))

