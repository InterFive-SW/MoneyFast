import importlib
import pkgutil
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

app = FastAPI(
    title="MoneyFast API",
    description="Modüler monolit kişisel finans danışmanı backend'i",
    version="0.1.0",
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
    async def spa_fallback(full_path: str) -> FileResponse:
        file_path = _static_dir / full_path
        if file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(_static_dir / "index.html"))
