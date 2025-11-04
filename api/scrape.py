"""Endpoints relacionados ao scraping."""
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from loguru import logger

from config import get_settings
from runner import run_scrape
from store import Repo

# Importar manager do server.py (será injetado)
manager = None


def set_manager(mgr: Any) -> None:
    """Define o manager de scraping."""
    global manager
    manager = mgr


router = APIRouter(prefix="/scrape", tags=["scrape"])

# Router sem prefix para /status
status_router = APIRouter(tags=["scrape"])


@status_router.get("/status")
async def get_status() -> dict:
    """Retorna o status do scraping."""
    return {"running": manager.running, **manager.last_status}


@router.post("/start")
async def start_scrape(payload: dict) -> dict:
    """Inicia o scraping."""
    url = payload.get("url")
    max_items = int(payload.get("max_items", 50))
    headless = payload.get("headless", True)
    category = payload.get("category")
    
    if not url:
        raise HTTPException(400, "url é obrigatório")
    
    # Limpar URL: remover espaços e caracteres extras
    url = url.strip()
    # Remover dois pontos e espaços no início se houver
    if url.startswith(":"):
        url = url[1:].strip()
    # Garantir que começa com http
    if not url.startswith("http"):
        raise HTTPException(400, f"URL inválida: {url}")
    
    if manager.running:
        raise HTTPException(409, "Scrape em execução")
    
    # Aplicar configuração de headless
    settings = get_settings()
    settings.headless = headless
    
    await manager.start(url=url, max_items=max_items, category=category, settings=settings)
    return {"ok": True}


@router.post("/stop")
async def stop_scrape() -> dict:
    """Para o scraping em andamento."""
    try:
        await manager.stop()
        return {"ok": True}
    except Exception as e:
        logger.error(f"Erro ao parar scraping: {e}")
        raise HTTPException(500, f"Erro ao parar: {e}")


