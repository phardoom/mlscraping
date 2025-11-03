"""Teste com output em arquivo"""
import asyncio
import json
from pathlib import Path
from browser import BrowserSession
from config import get_settings
from scraper import collect_product_urls_from_listing, extract_share_link
from logging_setup import setup_logging
from loguru import logger

setup_logging()

async def test_with_output():
    """Testa extração e salva resultados em arquivo"""
    settings = get_settings()
    settings.headless = False
    
    results = {
        "urls_collected": [],
        "extractions": []
    }
    
    url_listing = "https://www.mercadolivre.com.br/mais-vendidos/MLB5726"
    
    logger.info(f"Testando extração de links...")
    
    try:
        async with BrowserSession(settings) as session:
            page = await session.new_page()
            
            # Coletar URLs
            logger.info("Coletando URLs...")
            product_urls = await collect_product_urls_from_listing(
                page, url_listing, max_items=2, rate_ms=500
            )
            
            results["urls_collected"] = product_urls
            logger.info(f"Coletadas {len(product_urls)} URLs")
            
            # Extrair links
            for i, purl in enumerate(product_urls, 1):
                logger.info(f"\nProcessando produto {i}/{len(product_urls)}")
                
                try:
                    await page.goto(purl)
                    await page.wait_for_load_state("networkidle")
                    await asyncio.sleep(3)
                    
                    share_link = await extract_share_link(page)
                    
                    results["extractions"].append({
                        "url": purl,
                        "share_link": share_link,
                        "success": share_link is not None
                    })
                    
                    logger.info(f"Resultado: {'✅ Sucesso' if share_link else '❌ Falhou'}")
                    if share_link:
                        logger.info(f"Link: {share_link[:80]}...")
                        
                except Exception as e:
                    logger.error(f"Erro: {e}")
                    results["extractions"].append({
                        "url": purl,
                        "share_link": None,
                        "success": False,
                        "error": str(e)
                    })
    
    finally:
        # Salvar resultados
        output_file = Path("test_results.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        logger.info(f"\n✅ Resultados salvos em: {output_file}")
        logger.info(f"URLs coletadas: {len(results['urls_collected'])}")
        logger.info(f"Extrações bem-sucedidas: {sum(1 for e in results['extractions'] if e['success'])}")

if __name__ == "__main__":
    asyncio.run(test_with_output())

