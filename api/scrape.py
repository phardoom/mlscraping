"""Endpoints relacionados ao scraping."""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from loguru import logger

from config import get_settings

router = APIRouter(prefix="/scrape", tags=["scrape"])

# Manager será injetado via variável global
_manager: Any = None


def set_manager(manager: Any) -> None:
    """Define o manager global para as rotas."""
    global _manager
    _manager = manager


@router.post("/start")
async def start_scrape(payload: dict) -> dict:
    """Inicia o scraping."""
    if _manager is None:
        raise HTTPException(500, "Manager não inicializado")
    
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
    
    if _manager.running:
        raise HTTPException(409, "Scrape em execução")
    
    # Aplicar configuração de headless
    settings = get_settings()
    settings.headless = headless
    
    await _manager.start(url=url, max_items=max_items, category=category, settings=settings)
    return {"ok": True}


@router.post("/stop")
async def stop_scrape() -> dict:
    """Para o scraping em andamento."""
    if _manager is None:
        raise HTTPException(500, "Manager não inicializado")
    
    try:
        await _manager.stop()
        return {"ok": True}
    except Exception as e:
        logger.error(f"Erro ao parar scraping: {e}")
        raise HTTPException(500, f"Erro ao parar: {e}")


@router.get("/status")
async def status() -> dict:
    """Retorna o status atual do scraping."""
    if _manager is None:
        raise HTTPException(500, "Manager não inicializado")
    
    return {"running": _manager.running, **_manager.last_status}
