import importlib
import pkgutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.scheduler import start_scheduler, stop_scheduler
from app.modules.market import stream

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    FastAPI uygulamasının yaşam döngüsü yöneticisi (Lifespan).
    
    MİMARİ KARAR:
    Eskiden kullanılan @app.on_event("startup") yerine modern FastAPI uygulamalarında 
    'lifespan' context manager'ı önerilmektedir. Bu yapı, uygulama başlarken ve kapanırken 
    gerekli olan kaynakların (veritabanı bağlantıları, background scheduler vb.) 
    güvenli bir şekilde ayağa kaldırılmasını ve sonlandırılmasını (Graceful Shutdown) sağlar.
    Uygulama çöktüğünde veya kapatıldığında 'yield' sonrasındaki kısım çalışır ve hafıza 
    sızıntılarını önler.
    """
    # 1. Market veri akışını yapılandır (Canlı fiyatlar için)
    configure_market_stream()
    
    # 2. APScheduler'ı başlat. Arka planda Daily News dahil tüm periyodik görevleri yönetir.
    start_scheduler()
    
    yield
    
    # Graceful Shutdown: Uygulama kapanırken arkadaki scheduler işlemleri
    # durdurulur ve referans BIRAKILIR -- kapanmış bir event loop'u tutan bir
    # scheduler nesnesi, ikinci bir yaşam döngüsünde iş eklenemez hâle
    # geliyordu.
    stop_scheduler()

app = FastAPI(
    title="MoneyFast API",
    description="Modüler monolit kişisel finans danışmanı backend'i",
    version="0.1.0",
    lifespan=lifespan,
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


def configure_market_stream() -> None:
    """Give the SSE fan-out a way to read quotes.

    Injected rather than imported inside the stream module, so that module
    holds no database dependency and can be tested without a session.
    """
    from app.core.database import SessionLocal
    from app.modules.investment import market_service
    from app.modules.market import stream

    def read_frame():
        db = SessionLocal()
        try:
            quotes = market_service.latest_quotes(db)
            as_of, delay, is_delayed, is_stale = market_service.freshness(quotes)
            return {
                "as_of": as_of.isoformat() if as_of else None,
                "delay_minutes": delay,
                "is_delayed": is_delayed,
                "quotes": {
                    symbol: {
                        "price": row["price"],
                        "change": row.get("change_amount"),
                        "changePercent": row.get("change_percent"),
                        # Carried so the live overlay cannot strip the unit off
                        # a row it updates.
                        "currency": row.get("currency") or "TRY",
                    }
                    for symbol, row in quotes.items()
                },
            }
        finally:
            db.close()

    stream.configure(read_frame)

# Yüklenen statik dosyaları (özellikle kullanıcı avatar'larını) dışa açmak için mount işlemi.
# Bu klasör projenin kök dizinindeki 'uploads' dizinine işaret eder.
# Güvenlik Notu: Yalnızca resim dosyalarına erişim sağlanacağından, 
# executable (örn: .py, .sh) barındırılmaması önemlidir.
import os
from fastapi.staticfiles import StaticFiles

uploads_dir = Path(__file__).parent.parent / "uploads"
os.makedirs(uploads_dir / "avatars", exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

_static_dir = Path(__file__).parent.parent / "frontend" / "dist"
if not _static_dir.exists():
    _static_dir = Path(__file__).parent.parent.parent / "frontend" / "dist"

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

