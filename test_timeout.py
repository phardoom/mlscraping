"""Teste simples para verificar se o timeout está funcionando"""
import asyncio
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from browser import BrowserSession
from config import get_settings
from scraper import extract_share_link
from logging_setup import setup_logging
from loguru import logger

setup_logging()

async def test_timeout():
    """Testa se a função retorna dentro do timeout de 30s"""
    settings = get_settings()
    settings.headless = True  # Mais rápido
    
    logger.info("🧪 Teste de timeout iniciado")
    logger.info("⏱️ Timeout máximo configurado: 30 segundos")
    
    start_time = time.time()
    
    try:
        async with BrowserSession(settings) as session:
            page = await session.new_page()
            
            url = "https://www.mercadolivre.com.br/chaleira-eletrica-atacama-18l-unitermi/p/MLB13409956"
            logger.info(f"🌐 Navegando para: {url}")
            await page.goto(url, timeout=60000)
            await page.wait_for_load_state("networkidle", timeout=30000)
            
            logger.info("🔍 Iniciando extração de link...")
            result = await extract_share_link(page)
            
            elapsed = time.time() - start_time
            
            if result:
                logger.success(f"✅ SUCESSO: Link extraído em {elapsed:.1f}s")
                logger.info(f"📎 Link: {result[:60]}...")
            else:
                logger.warning(f"⚠️ AVISO: Nenhum link encontrado após {elapsed:.1f}s")
            
            if elapsed > 35:
                logger.error(f"❌ FALHA: Função demorou {elapsed:.1f}s (acima do timeout de 30s)")
                return False
            else:
                logger.success(f"✅ PASS: Função retornou em {elapsed:.1f}s (dentro do timeout)")
                return True
                
    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        logger.error(f"❌ TIMEOUT: Função não retornou após {elapsed:.1f}s")
        return False
    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"❌ ERRO após {elapsed:.1f}s: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_timeout())
    sys.exit(0 if success else 1)

