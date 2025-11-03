"""Teste de debug para coleta de URLs"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from browser import BrowserSession
from config import get_settings
from scraper import collect_product_urls_from_listing
from logging_setup import setup_logging
from loguru import logger

setup_logging()

async def test_collect():
    """Testa a coleta de URLs com debug detalhado"""
    settings = get_settings()
    settings.headless = False  # Ver o navegador
    
    url = "https://www.mercadolivre.com.br/mais-vendidos/MLB5726"
    
    logger.info(f"Testando coleta de URLs de: {url}")
    
    async with BrowserSession(settings) as session:
        page = await session.new_page()
        
        logger.info("Navegando para a página...")
        urls = await collect_product_urls_from_listing(
            page, url, max_items=10, rate_ms=500
        )
        
        logger.info(f"✅ Total de URLs coletadas: {len(urls)}")
        
        if urls:
            logger.info("Primeiras URLs encontradas:")
            for i, u in enumerate(urls[:5], 1):
                logger.info(f"  {i}. {u}")
        else:
            logger.error("❌ Nenhuma URL encontrada!")
            
            # Verificar página
            try:
                title = await page.title()
                current_url = page.url
                logger.info(f"Título da página: {title}")
                logger.info(f"URL atual: {current_url}")
                
                # Contar links
                all_links = await page.eval_on_selector_all("a[href]", "els => els.length")
                logger.info(f"Total de links <a> na página: {all_links}")
                
                p_links = await page.eval_on_selector_all("a[href*='/p/']", "els => els.length")
                logger.info(f"Links com '/p/': {p_links}")
                
                # Esperar um pouco para o usuário ver
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Erro ao verificar: {e}")

if __name__ == "__main__":
    asyncio.run(test_collect())

