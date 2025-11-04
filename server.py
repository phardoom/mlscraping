from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from config import get_settings
from logging_setup import setup_logging
from scrape_manager import manager
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

# Montar arquivos estáticos
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def index() -> HTMLResponse:
    """Retorna a página HTML principal."""
    template_path = Path(__file__).parent / "templates" / "index.html"
    if not template_path.exists():
        return HTMLResponse("<h1>Template não encontrado</h1>", status_code=500)
    with template_path.open("r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/favicon.ico")
async def favicon() -> dict:
    """Ignora requisições de favicon."""
    return {}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    manager.clients.add(ws)
    try:
        await ws.send_json({"type": "hello", "running": manager.running})
        while True:
            # Mantém conexão viva; não esperamos mensagens do cliente
            await asyncio.sleep(60)
    except WebSocketDisconnect:
        pass
    finally:
        manager.clients.discard(ws)


# Registrar routers dos módulos de API
from api import products, scrape, whatsapp

app.include_router(scrape.router)
app.include_router(products.router)
app.include_router(whatsapp.router)


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)

