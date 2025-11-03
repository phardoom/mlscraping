from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Awaitable, Callable, Optional

from loguru import logger

from browser import BrowserSession
from config import Settings
from messages import format_whatsapp_message
from models import AffiliateLink, Message
from scraper import (
    build_affiliate_link,
    build_short_link_from_id,
    collect_product_urls_from_listing,
    download_image,
    extract_product_data,
    extract_share_link,
    passes_filters,
)
from store import Repo


ProgressCb = Callable[[dict], Awaitable[None]]


async def run_scrape(
    settings: Settings,
    repo: Repo,
    *,
    url: str,
    max_items: int,
    category: Optional[str] = None,
    progress: Optional[ProgressCb] = None,
) -> None:
    """Executa o scraping de ponta a ponta com callbacks de progresso.

    Args:
        settings: configurações globais
        repo: repositório para persistir resultados
        url: URL de listagem (ex.: Mais vendidos)
        max_items: limite de itens
        progress: callback assíncrono que recebe dicionários serializáveis
    """

    async def emit(event: dict) -> None:
        if progress:
            try:
                await progress(event)
            except Exception:  # noqa: BLE001
                logger.debug("Falha ao enviar evento de progresso")

    await emit({"type": "start", "url": url, "max": max_items})
    try:
        async with BrowserSession(settings) as session:
            page = await session.new_page()
            logger.info(f"Iniciando coleta de URLs da listagem: {url}")
            await emit({"type": "status_message", "message": f"Navegando para: {url}"})
            
            product_urls = await collect_product_urls_from_listing(
                page, url, max_items=max_items, rate_ms=settings.rate_limit_ms
            )
            
            logger.info(f"URLs coletadas: {len(product_urls)}")
            await emit({"type": "list_collected", "count": len(product_urls)})
            
            if len(product_urls) == 0:
                error_msg = f"Nenhum produto encontrado na URL: {url}. Verifique se a URL está correta e se há produtos na página."
                logger.warning(error_msg)
                await emit({"type": "error", "message": error_msg})
                return

            for idx, purl in enumerate(product_urls, start=1):
                await emit({"type": "item_begin", "index": idx, "total": len(product_urls), "url": purl})
                
                # Aguarda um pouco antes de processar o próximo produto (se não for o primeiro)
                if idx > 1:
                    await asyncio.sleep(1.0)  # Aumentado para garantir que a página anterior finalizou
                
                try:
                    logger.debug(f"Chamando extract_product_data para: {purl}")
                    p = await extract_product_data(page, purl)
                    # Aplica categoria se fornecida
                    if category:
                        p.category = category
                    logger.info(f"✅ Dados do produto extraídos: {p.title[:50]}... (ID: {p.id_meli})")
                except Exception as e:  # noqa: BLE001
                    logger.error(f"❌ Erro ao extrair dados do produto {purl}: {e}")
                    await emit({"type": "item_error", "url": purl, "error": str(e)})
                    continue
                
                logger.debug(f"Verificando filtros para produto {p.id_meli}...")
                if not passes_filters(settings, p):
                    logger.debug(f"Produto {p.id_meli} filtrado - pulando")
                    await emit({"type": "item_filtered", "id": p.id_meli})
                    continue
                
                logger.debug(f"Produto {p.id_meli} passou nos filtros. Iniciando extração de link...")

                # Tenta pegar link pelo Compartilhar com fallbacks
                share = None
                
                # Estratégia 1: Extrair do botão Compartilhar
                try:
                    logger.info(f"Tentando extrair link compartilhado para produto {idx}/{len(product_urls)}: {purl}")
                    logger.debug(f"Iniciando extract_share_link para: {purl}")
                    # Timeout total de 12 segundos (MAX_EXTRACTION_TIME interno é 10s + margem)
                    share = await asyncio.wait_for(extract_share_link(page), timeout=12.0)
                    logger.debug(f"extract_share_link concluído. Resultado: {'Link encontrado' if share else 'Link não encontrado'}")
                    if share:
                        logger.info(f"✅ Link compartilhado extraído com sucesso: {share[:60]}...")
                    else:
                        logger.warning(f"⚠️ Link compartilhado não encontrado para {purl}")
                    # Aguarda um pouco após extrair o link
                    await asyncio.sleep(0.5)  # Aumentado para garantir estabilização
                except asyncio.TimeoutError:
                    logger.error(f"⏱️ Timeout ao extrair link compartilhado após 12s para {purl}")
                    share = None
                except Exception as e:  # noqa: BLE001
                    logger.error(f"Erro ao extrair link compartilhado: {e}")
                    share = None
                    await asyncio.sleep(0.3)  # Reduzido de 1s para 0.3s
                
                # Estratégia 2: Construir link limpo a partir da URL (fallback)
                if not share:
                    try:
                        logger.debug("Tentando construir link limpo como fallback")
                        share = build_short_link_from_id(purl)
                        if share:
                            logger.info(f"Link limpo gerado como fallback: {share[:60]}...")
                    except Exception as e:  # noqa: BLE001
                        logger.debug(f"Erro ao construir link limpo: {e}")
                        share = None
                
                # Estratégia 3: Usar build_affiliate_link como último recurso
                if not share:
                    logger.debug("Usando build_affiliate_link como último recurso")
                    share = build_affiliate_link(settings, purl)

                img_path: Optional[Path] = None
                if p.image_url:
                    img_path = await download_image(str(p.image_url), settings.images_dir / f"{p.id_meli}.jpg")

                repo.upsert_product(p)
                repo.upsert_link(p.id_meli, AffiliateLink(source_url=p.url, final_url=share))
                msg_text = format_whatsapp_message(p, share)
                repo.upsert_message(Message(product_id=p.id_meli, text=msg_text, image_path=str(img_path) if img_path else None))
                await emit({"type": "item_saved", "id": p.id_meli, "title": p.title, "share": share})

            repo.export_csv_json_messages(settings.out_dir)
            await emit({"type": "end"})
    except Exception as e:  # noqa: BLE001
        error_msg = f"Erro durante o scraping: {str(e)}"
        logger.exception(error_msg)
        await emit({"type": "error", "message": error_msg})
        await emit({"type": "end"})

