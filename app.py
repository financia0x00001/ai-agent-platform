from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from config import settings
from routers import llm_config, project, ws, delivery, approval

app = FastAPI(title=settings.app_name, version=settings.app_version)


@app.get("/health")
async def health():
    """健康检查端点"""
    from config import get_default_llm
    llm_ok = get_default_llm() is not None
    return {
        "status": "ok",
        "version": settings.app_version,
        "llm_configured": llm_ok,
    }

app.include_router(llm_config.router)
app.include_router(project.router)
app.include_router(ws.router)
app.include_router(delivery.router)
app.include_router(approval.router)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
