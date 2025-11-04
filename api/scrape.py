"""Endpoints relacionados ao scraping."""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from loguru import logger

from api.schemas import (
    ScrapeStartRequest,
    ScrapeStartResponse,
    ScrapeStopResponse,
    StatusResponse,
)
from config import get_settings
from runner import run_scrape
from store import Repo


class ScrapeManager:
    def __init__(self) -> None:
        self.running: bool = False
        self.task: asyncio.Task[Any] | None = None
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

    async def start(self, *, url: str, max_items: int, category: str | None = None, settings: Any | None = None) -> None:
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


# Instância global do manager
manager = ScrapeManager()


def create_router() -> APIRouter:
    """Cria router com endpoints de scraping."""
    router = APIRouter()

    @router.post("/scrape/start", response_model=ScrapeStartResponse)
    async def start_scrape(request: ScrapeStartRequest) -> ScrapeStartResponse:
        """Inicia um novo scraping."""
        if manager.running:
            raise HTTPException(409, "Scrape em execução")
        
        # Aplicar configuração de headless
        settings = get_settings()
        settings.headless = request.headless
        
        await manager.start(
            url=request.url,
            max_items=request.max_items,
            category=request.category,
            settings=settings,
        )
        return ScrapeStartResponse(ok=True)

    @router.post("/scrape/stop", response_model=ScrapeStopResponse)
    async def stop_scrape() -> ScrapeStopResponse:
        """Para o scraping em andamento."""
        try:
            await manager.stop()
            return ScrapeStopResponse(ok=True)
        except Exception as e:
            logger.error(f"Erro ao parar scraping: {e}")
            raise HTTPException(500, f"Erro ao parar: {e}")

    @router.get("/status", response_model=StatusResponse)
    async def status() -> StatusResponse:
        """Retorna o status atual do scraping."""
        return StatusResponse(running=manager.running, **manager.last_status)

    @router.websocket("/ws")
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

    return router
