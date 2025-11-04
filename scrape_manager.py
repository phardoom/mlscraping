"""Gerenciador de scraping."""
import asyncio
from typing import Any, Optional

from fastapi import WebSocket
from loguru import logger

from config import get_settings
from runner import run_scrape
from store import Repo


class ScrapeManager:
    """Gerencia o estado e execução de scrapings."""
    
    def __init__(self) -> None:
        self.running: bool = False
        self.task: Optional[asyncio.Task[Any]] = None
        self.clients: set[WebSocket] = set()
        self.last_status: dict[str, Any] = {"running": False}

    async def broadcast(self, data: dict) -> None:
        """Envia mensagem para todos os clientes WebSocket conectados."""
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
        """Inicia um novo scraping."""
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


# Instância global do gerenciador
manager = ScrapeManager()
