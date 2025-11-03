"""Teste rápido da extração de links"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from browser import BrowserSession
from config import get_settings
from scraper import collect_product_urls_from_listing, extract_share_link
from logging_setup import setup_logging
from loguru import logger

setup_logging()

async def test_extraction():
    """Testa a extração completa de links"""
    settings = get_settings()
    settings.headless = False  # Para ver o que está acontecendo
    
    logger.info("🧪 Iniciando teste de extração de links...")
    
    url_listing = "https://www.mercadolivre.com.br/mais-vendidos/MLB5726"
    
    async with BrowserSession(settings) as session:
        page = await session.new_page()
        
        # 1. Coletar URLs dos produtos
        logger.info(f"📋 Coletando URLs da listagem: {url_listing}")
        product_urls = await collect_product_urls_from_listing(
            page, url_listing, max_items=3, rate_ms=500
        )
        
        logger.info(f"✅ {len(product_urls)} URLs coletadas")
        for i, purl in enumerate(product_urls, 1):
            logger.info(f"  {i}. {purl[:80]}...")
        
        # 2. Para cada produto, extrair link de compartilhamento
        logger.info("\n🔗 Testando extração de links de compartilhamento...")
        for i, purl in enumerate(product_urls, 1):
            logger.info(f"\n--- Produto {i}/{len(product_urls)} ---")
            logger.info(f"URL: {purl}")
            
            try:
                await page.goto(purl)
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2)  # Aguarda página carregar
                
                # Extrair link usando o botão azul da barra superior
                share_link = await extract_share_link(page)
                
                if share_link:
                    logger.success(f"✅ Link extraído: {share_link}")
                else:
                    logger.warning("⚠️ Link não encontrado")
                    
            except Exception as e:
                logger.error(f"❌ Erro ao processar {purl}: {e}")
                continue
    
    logger.info("\n✅ Teste concluído!")

if __name__ == "__main__":
    asyncio.run(test_extraction())

