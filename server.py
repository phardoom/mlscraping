from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from api import products, scrape, whatsapp
from config import get_settings
from logging_setup import setup_logging
from store import Repo


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia o ciclo de vida da aplicação."""
    # Startup
    setup_logging()
    settings = get_settings()
    # Garante pastas
    settings.out_dir.mkdir(parents=True, exist_ok=True)
    settings.images_dir.mkdir(parents=True, exist_ok=True)
    settings.state_path.parent.mkdir(parents=True, exist_ok=True)
    Repo(settings.db_path).init()
    yield
    # Shutdown (se necessário)


app = FastAPI(title="ML Scraper UI", version="0.1.0", lifespan=lifespan)

# Registrar routers dos módulos API
app.include_router(scrape.create_router())
app.include_router(products.create_router())
app.include_router(whatsapp.create_router())

# Servir arquivos estáticos
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.get("/")
async def index() -> HTMLResponse:
    """Serve o template HTML principal."""
    template_path = Path(__file__).parent / "templates" / "index.html"
    if template_path.exists():
        with template_path.open("r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(html_content)
    return HTMLResponse("<h1>Template não encontrado</h1>")


@app.get("/favicon.ico")
async def favicon() -> dict:
    """Ignora requisições de favicon."""
    return {}


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
