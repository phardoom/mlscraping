"""Teste rápido para verificar timeout na extração de link"""
import asyncio
import sys
from pathlib import Path

# Adiciona o diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent))

from browser import BrowserSession
from config import get_settings
from scraper import extract_share_link
from logging_setup import setup_logging
from loguru import logger

# Configura logging
setup_logging()

async def test_extract():
    """Testa a extração de link com timeout"""
    settings = get_settings()
    settings.headless = False  # Para ver o que está acontecendo
    
    logger.info("Iniciando teste de extração de link...")
    
    async with BrowserSession(settings) as session:
        page = await session.new_page()
        
        # Navega para a página do produto
        url = "https://www.mercadolivre.com.br/chaleira-eletrica-atacama-18l-unitermi/p/MLB13409956"
        logger.info(f"Navegando para: {url}")
        await page.goto(url)
        await page.wait_for_load_state("networkidle")
        
        # Tenta extrair o link
        logger.info("Tentando extrair link compartilhado...")
        import time
        start = time.time()
        
        try:
            share_link = await extract_share_link(page)
            elapsed = time.time() - start
            
            if share_link:
                logger.success(f"✅ Link extraído com sucesso em {elapsed:.1f}s")
                logger.info(f"Link: {share_link[:80]}...")
            else:
                logger.warning(f"⚠️ Nenhum link encontrado após {elapsed:.1f}s")
                
        except Exception as e:
            elapsed = time.time() - start
            logger.error(f"❌ Erro após {elapsed:.1f}s: {e}")
            import traceback
            traceback.print_exc()
        
        logger.info(f"Teste concluído em {elapsed:.1f}s")

if __name__ == "__main__":
    asyncio.run(test_extract())

