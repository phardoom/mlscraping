"""Teste simples e direto da extração"""
import asyncio
from browser import BrowserSession
from config import get_settings
from scraper import extract_share_link
from logging_setup import setup_logging
from loguru import logger

setup_logging()

async def test_simple():
    """Testa extração em um produto específico"""
    settings = get_settings()
    settings.headless = False
    
    url = "https://www.mercadolivre.com.br/chaleira-eletrica-atacama-18l-unitermi/p/MLB13409956"
    
    logger.info(f"Testando extração para: {url}")
    
    async with BrowserSession(settings) as session:
        page = await session.new_page()
        await page.goto(url)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)
        
        logger.info("Tentando extrair link de compartilhamento...")
        share_link = await extract_share_link(page)
        
        if share_link:
            logger.success(f"SUCESSO! Link: {share_link}")
        else:
            logger.error("FALHOU! Link não encontrado")
    
    logger.info("Teste finalizado")

if __name__ == "__main__":
    asyncio.run(test_simple())

