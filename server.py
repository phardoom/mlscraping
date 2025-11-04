from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from api import categories, products, scrape, whatsapp
from config import get_settings
from logging_setup import setup_logging
from runner import run_scrape
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
app.mount("/static", StaticFiles(directory="static"), name="static")


class ScrapeManager:
    def __init__(self) -> None:
        self.running: bool = False
        self.task: Optional[asyncio.Task[Any]] = None
        self.clients: set[WebSocket] = set()
        self.last_status: dict[str, Any] = {"running": False}

    async def broadcast(self, data: dict) -> None:
        self.last_status.update(data if isinstance(data, dict) else {})
        stale: list[WebSocket] = []
        for ws in self.clients:
            try:
                await ws.send_json(data)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.clients.discard(ws)

    async def start(self, *, url: str, max_items: int, category: Optional[str] = None, settings: Optional[Any] = None) -> None:
        if self.running:
            raise RuntimeError("Scrape já em execução")

        if settings is None:
            settings = get_settings()
        settings.max_items = max_items
        repo = Repo(settings.db_path)
        repo.init()

        async def progress(ev: dict) -> None:
            await self.broadcast(ev)

        async def runner() -> None:
            self.running = True
            try:
                await self.broadcast({"type": "status", "running": True})
                await run_scrape(settings, repo, url=url, max_items=max_items, category=category, progress=progress)
            except Exception as e:  # noqa: BLE001
                logger.exception("Erro no scraping")
                await self.broadcast({"type": "error", "message": str(e)})
            finally:
                self.running = False
                await self.broadcast({"type": "status", "running": False})

        self.task = asyncio.create_task(runner())

    async def stop(self) -> None:
        """Para o scraping em andamento."""
        if not self.running:
            return  # Já está parado
        
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                logger.info("Scraping cancelado pelo usuário")
            except Exception as e:  # noqa: BLE001
                logger.debug(f"Erro ao parar scraping: {e}")
        
        self.running = False
        await self.broadcast({"type": "status", "running": False})


manager = ScrapeManager()

# Injetar manager no módulo de scrape
scrape.set_manager(manager)


@app.get("/")
async def index() -> HTMLResponse:
    """Serve a página principal."""
    template_path = Path("templates/index.html")
    if not template_path.exists():
        return HTMLResponse("<h1>Template não encontrado</h1>", status_code=500)
    
    with template_path.open("r", encoding="utf-8") as f:
        template_content = f.read()
    
    return HTMLResponse(template_content)


@app.get("/favicon.ico")
async def favicon() -> dict:
    """Ignora requisições de favicon."""
    return {}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    """WebSocket para atualizações em tempo real."""
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


# Registrar routers
app.include_router(scrape.router)
app.include_router(scrape.status_router)  # Status sem prefix
app.include_router(products.router)
app.include_router(whatsapp.router)
app.include_router(categories.router)


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
