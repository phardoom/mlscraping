"""Endpoints relacionados ao scraping."""
from fastapi import APIRouter, HTTPException
from loguru import logger

from scrape_manager import manager as scrape_manager

router = APIRouter(prefix="/scrape", tags=["scrape"])


@router.post("/start")
async def start_scrape(payload: dict) -> dict:
    """Inicia um novo scraping."""
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
    
    if scrape_manager.running:
        raise HTTPException(409, "Scrape em execução")
    
    # Aplicar configuração de headless
    from config import get_settings
    settings = get_settings()
    settings.headless = headless
    
    await scrape_manager.start(url=url, max_items=max_items, category=category, settings=settings)
    return {"ok": True}


@router.post("/stop")
async def stop_scrape() -> dict:
    """Para o scraping em andamento."""
    try:
        await scrape_manager.stop()
        return {"ok": True}
    except Exception as e:
        logger.error(f"Erro ao parar scraping: {e}")
        raise HTTPException(500, f"Erro ao parar: {e}")


@router.get("/status")
async def status() -> dict:
    """Retorna o status atual do scraping."""
    return {"running": scrape_manager.running, **scrape_manager.last_status}
