from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Iterable, Optional

import httpx
from loguru import logger
from playwright.async_api import Error as PWError, Page

from config import Settings
from models import AffiliateLink, Product


# Aceita múltiplos formatos de produto do ML (produto.mercadolivre.com.br, /p/ e /MLB- e /oferta/)
PRODUCT_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:mercadolivre|produto\.mercadolivre)\.com\.br/(?:.*?)(MLB-\d+|p/[A-Za-z0-9]+|oferta/[A-Za-z0-9\-]+)",
    re.IGNORECASE,
)


def extract_meli_id(url: str) -> str:
    m = re.search(r"(MLB-\d+)", url, re.IGNORECASE)
    if m:
        return m.group(1)
    m2 = re.search(r"/p/([A-Za-z0-9]+)", url)
    if m2:
        return m2.group(1)
    return url


async def collect_product_urls_from_listing(page: Page, url: str, max_items: int, rate_ms: int) -> list[str]:
    # Limpar URL antes de usar
    url = url.strip()
    if url.startswith(":"):
        url = url[1:].strip()
    
    if not url.startswith("http"):
        raise ValueError(f"URL inválida: {url}")
    
    logger.info(f"Navegando para: {url}")
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)  # 60s - aumentado
    except Exception as e:
        logger.error(f"Erro ao navegar para {url}: {e}")
        raise
    
    # Aguarda página carregar (não usa networkidle pois pode nunca acontecer)
    try:
        await page.wait_for_load_state("load", timeout=30000)  # 30s - aumentado
        await asyncio.sleep(1)  # Aguarda elementos dinâmicos
    except Exception:
        logger.debug("Timeout no wait_for_load_state, continuando mesmo assim...")
        await asyncio.sleep(1)
    
    logger.debug("Página carregada, procurando produtos...")
    # Aceitar cookies/consentimento se aparecer
    try:
        for label in ["Aceitar", "Continuar", "Entendi", "OK", "Ok", "Aceptar"]:
            loc = page.locator(f"button:has-text('{label}')")
            if await loc.count() > 0:
                await loc.first.click()
                await asyncio.sleep(0.5)
                break
    except Exception:
        pass
    
    # Rolagem progressiva para carregar mais itens
    last_height = 0
    urls: list[str] = []
    scroll_count = 0
    max_scrolls = 30
    
    logger.debug(f"Iniciando coleta de URLs da listagem: {url}")
    
    for scroll_count in range(max_scrolls):
        # Múltiplos seletores para encontrar produtos
        selectors = [
            "div[class*='ui-search-result'] a[href*='mercadolivre.com.br']",
            "div[class*='poly-card'] a[href*='mercadolivre.com.br']",
            "a[href*='/p/']",
            "a[href*='produto.mercadolivre.com.br']",
            "a[href*='mercadolivre.com.br'][href*='/p/']",
        ]
        
        all_anchors: list[str] = []
        for selector in selectors:
            try:
                anchors = await page.eval_on_selector_all(
                    selector,
                    "els => els.map(e => e.href)",
                )
                if anchors:
                    all_anchors.extend([a for a in anchors if isinstance(a, str)])
            except PWError:
                continue
        
        logger.debug(f"Scroll {scroll_count + 1}: encontrados {len(all_anchors)} anchors")
        
        # Filtrar URLs válidas de produtos
        product_urls_found = 0
        for a in all_anchors:
            if isinstance(a, str) and "mercadolivre.com.br" in a:
                clean_url = a.split("?")[0].split("#")[0]
                
                # Verifica se é URL de produto (múltiplos padrões)
                is_product_url = (
                    PRODUCT_URL_RE.search(clean_url) or  # Regex
                    "/p/" in clean_url or  # Formato /p/ID
                    "produto.mercadolivre.com.br" in clean_url or  # Subdomínio produto
                    re.search(r'/MLB-\d+', clean_url)  # Formato MLB-123456
                )
                
                if is_product_url and clean_url not in urls:
                    urls.append(clean_url)
                    product_urls_found += 1
        
        logger.debug(f"Scroll {scroll_count + 1}: {product_urls_found} novas URLs de produtos encontradas")
        logger.debug(f"Total de URLs únicas coletadas até agora: {len(urls)}")
        
        urls = list(dict.fromkeys(urls))  # dedup preservando ordem
        
        if len(urls) >= max_items:
            logger.info(f"Limite de {max_items} itens atingido após {scroll_count + 1} scrolls")
            break
        
        # Scroll para baixo
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(max(rate_ms / 1000, 1.5))  # Mínimo 1.5s entre scrolls
        
        new_height = await page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            logger.debug(f"Página não carregou mais conteúdo após scroll {scroll_count + 1}")
            break
        last_height = new_height

    logger.info(f"URLs coletadas na listagem: {len(urls)} (após {scroll_count + 1} scrolls)")
    
    if len(urls) == 0:
        logger.warning("⚠️ Nenhuma URL de produto encontrada! Verificando página...")
        # Debug: verificar se a página carregou corretamente
        try:
            page_title = await page.title()
            page_url = page.url
            logger.warning(f"Título da página: {page_title}")
            logger.warning(f"URL atual: {page_url}")
            
            # Tentar contar quantos links existem na página
            all_links = await page.eval_on_selector_all("a[href]", "els => els.length")
            logger.warning(f"Total de links <a> na página: {all_links}")
            
            # Tentar encontrar links com /p/
            p_links = await page.eval_on_selector_all("a[href*='/p/']", "els => els.length")
            logger.warning(f"Links com '/p/' encontrados: {p_links}")
            
            # Mostrar alguns exemplos de links encontrados
            sample_links = await page.eval_on_selector_all(
                "a[href*='mercadolivre.com.br']",
                "els => els.slice(0, 5).map(e => e.href)"
            )
            logger.warning(f"Exemplos de links encontrados: {sample_links}")
        except Exception as e:
            logger.debug(f"Erro ao verificar página: {e}")
    
    return urls[:max_items]


async def _close_modal(page: Page) -> None:
    """Fecha o modal de compartilhamento se estiver aberto. Rápido e sem delays."""
    try:
        # Verifica se há modal aberto (rápido, sem esperas)
        try:
            dialog_loc = page.locator("role=dialog")
            dialog_count = await asyncio.wait_for(dialog_loc.count(), timeout=0.5)
            if dialog_count == 0:
                return  # Nenhum modal aberto
        except (asyncio.TimeoutError, Exception):
            return  # Se demorar ou erro, assume que não há modal
        
        # Tenta fechar rapidamente - apenas ESC (mais rápido)
        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.2)  # Reduzido para 0.2s
        except Exception:
            pass
        
        # Se ainda estiver aberto, tenta botões de fechar
        close_selectors = [
            "role=dialog button[aria-label*='Fechar']",
            "role=dialog button[aria-label*='Close']",
        ]
        for close_sel in close_selectors:
            try:
                close_loc = page.locator(close_sel)
                count = await asyncio.wait_for(close_loc.count(), timeout=0.3)
                if count > 0:
                    await close_loc.first.click(timeout=1000)
                    await asyncio.sleep(0.2)  # Reduzido
                    return
            except (asyncio.TimeoutError, Exception):
                continue
    except Exception:
        pass  # Ignora erros - não crítico


async def extract_share_link(page: Page) -> Optional[str]:
    """Tenta obter o link pelo botão Compartilhar. Retorna None se falhar."""
    
    logger.info("🚀 INICIANDO extração do link compartilhado")
    
    # Timeout máximo para evitar loops infinitos
    import time
    start_time = time.time()
    MAX_EXTRACTION_TIME = 10  # 10 segundos máximo - com delays para garantir carregamento
    
    def check_timeout() -> bool:
        """Verifica se excedeu o tempo máximo"""
        elapsed = time.time() - start_time
        if elapsed > MAX_EXTRACTION_TIME:
            logger.warning(f"⏱️ Timeout na extração após {elapsed:.1f}s")
            return True
        return False
    
    # PRIMEIRO: Fechar qualquer modal aberto rapidamente (com timeout)
    logger.debug("Passo 1: Fechando modais abertos...")
    try:
        # Usa asyncio.wait_for para garantir que não trave
        logger.debug("Chamando _close_modal com timeout de 1s...")
        await asyncio.wait_for(_close_modal(page), timeout=1.0)
        logger.debug("✅ Passo 1 concluído - modais fechados")
    except asyncio.TimeoutError:
        logger.debug("⏱️ Passo 1 timeout após 1s (ignorando e continuando)")
    except Exception as e:
        logger.debug(f"⚠️ Erro ao fechar modal (ignorando): {e}")
    
    if check_timeout():
        return None
    
    # SEGUNDO: Scrollar para o topo instantaneamente
    logger.debug("Passo 2: Scrollando para o topo...")
    try:
        await page.evaluate("window.scrollTo(0, 0)")
        logger.debug("✅ Passo 2 concluído - scroll para topo")
    except Exception as e:
        logger.debug(f"⚠️ Erro ao scrollar (ignorando): {e}")
    
    # TERCEIRO: Buscar botão - apenas o seletor que funciona melhor
    logger.debug("Passo 3: Buscando botão Compartilhar...")
    button_found = False
    # Usa apenas o seletor que funciona melhor (data-testid)
    sel = "[data-testid='generate_link_button']"
    
    try:
        logger.debug(f"Buscando botão com seletor: {sel}")
        # Tenta encontrar o botão SEM wait_for (mais rápido)
        loc = page.locator(sel)
        count = await asyncio.wait_for(loc.count(), timeout=1.0)  # Máximo 1s para contar
        logger.debug(f"✅ Botões encontrados com {sel}: {count}")
        
        if count > 0:
            logger.debug(f"✅ Botão encontrado: {sel}")
            try:
                # Verifica se está visível rapidamente
                is_visible = await asyncio.wait_for(loc.first.is_visible(), timeout=0.5)
                if not is_visible:
                    await loc.first.scroll_into_view_if_needed()
                    await asyncio.sleep(0.1)  # Mínimo delay
                
                logger.debug("Clicando no botão...")
                await loc.first.click(timeout=2000)  # Timeout de 2s no click
                button_found = True
                await asyncio.sleep(0.5)  # Aguarda processamento do clique
                logger.debug("✅ Botão clicado!")
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"Erro ao clicar: {e}")
    except (asyncio.TimeoutError, Exception) as e:
        logger.debug(f"Botão não encontrado rapidamente: {e}")
    
    # Fallback: tentar outros seletores rapidamente
    if not button_found:
        logger.debug("Botão não encontrado com seletor principal, tentando fallbacks...")
        fallback_selectors = [
            "nav[aria-label='Afiliados'] button:has-text('Compartilhar')",
            "button:has-text('Compartilhar')",
        ]
        for sel in fallback_selectors:
            if check_timeout():
                logger.warning("Timeout ao buscar botão - retornando None")
                return None
            try:
                loc = page.locator(sel)
                count = await loc.count()
                if count > 0:
                    logger.debug(f"Botão encontrado com fallback: {sel}")
                    await loc.first.click(timeout=2000)
                    button_found = True
                    break
            except Exception:
                continue
    
    if not button_found:
        logger.warning("❌ Botão Compartilhar não encontrado")
        return None
    
    # QUARTO: Aguardar modal aparecer e carregar completamente
    logger.debug("Passo 4: Aguardando modal aparecer...")
    try:
        await asyncio.wait_for(
            page.wait_for_selector("role=dialog", timeout=3000, state="visible"),
            timeout=3.1
        )
        logger.debug("✅ Modal detectado! Aguardando carregamento completo...")
        # Aguarda o modal carregar completamente com o link
        await asyncio.sleep(1.0)  # Aumentado para garantir que o link esteja disponível
    except (asyncio.TimeoutError, Exception):
        try:
            await asyncio.wait_for(
                page.wait_for_selector("[role='dialog']", timeout=2000, state="visible"),
                timeout=2.1
            )
            logger.debug("✅ Modal detectado via fallback! Aguardando carregamento...")
            await asyncio.sleep(1.0)
        except (asyncio.TimeoutError, Exception):
            logger.debug("Modal não detectado, tentando mesmo assim...")
            await asyncio.sleep(0.5)
    
    if check_timeout():
        logger.warning("Timeout após aguardar modal - retornando None")
        return None

    # ESTRATÉGIA PRINCIPAL (MESMA DO TESTE MANUAL): Clicar no botão "Link do produto" e ler do clipboard
    logger.debug("Passo 5: Clicando no botão 'Link do produto' para copiar...")
    try:
        # Usa o mesmo seletor que funcionou no teste manual
        copy_button = page.locator("[data-testid='copy-button__label_link']")
        count = await asyncio.wait_for(copy_button.count(), timeout=1.0)
        
        if count > 0:
            logger.debug("Botão 'Link do produto' encontrado, clicando...")
            await copy_button.first.click(timeout=2000)
            logger.debug("Botão clicado, aguardando cópia...")
            
            # Aguarda clipboard atualizar completamente
            await asyncio.sleep(0.8)  # Aumentado para garantir que clipboard seja atualizado
            
            # Lê do clipboard (mesma estratégia do teste manual)
            text = await page.evaluate("() => navigator.clipboard.readText()")
            if isinstance(text, str) and text.startswith("http"):
                # CRÍTICO: Verifica se é link compartilhado (/sec/)
                if "/sec/" in text or "mercadolivre.com/sec/" in text:
                    url_match = re.search(r'https?://[^\s]*mercadolivre\.com/sec/[^\s]+', text)
                    if url_match:
                        link = url_match.group(0).rstrip('.,;:!?')
                        logger.info(f"✅ Link copiado do clipboard: {link[:60]}...")
                        await _close_modal(page)
                        return link
                    else:
                        logger.debug(f"Link copiado não é /sec/ válido: {text[:50]}...")
                else:
                    logger.debug(f"Link copiado não contém /sec/ (é URL completa): {text[:50]}...")
            else:
                logger.debug(f"Texto copiado não é um link válido: {text[:50] if text else 'None'}...")
        else:
            logger.debug("Botão 'Link do produto' não encontrado")
    except Exception as e:
        logger.debug(f"Erro ao clicar no botão 'Link do produto': {e}")
    
    # Se chegou aqui, a estratégia principal falhou
    # Retorna None para usar o fallback (URL limpa construída)
    logger.debug("❌ Estratégia principal falhou - retornando None para usar fallback")
    await _close_modal(page)
    return None


async def extract_product_data(page: Page, url: str) -> Product:
    """Extrai dados mínimos do produto: título, preço e imagem. Otimizado para velocidade."""
    logger.debug(f"Extraindo dados do produto: {url}")
    
    # Navegação rápida com timeout agressivo
    try:
        await asyncio.wait_for(
            page.goto(url, wait_until="domcontentloaded", timeout=15000),
            timeout=15.0
        )
        logger.debug("DOM carregado")
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning(f"Timeout ao navegar para {url}, tentando continuar: {e}")
    
    # Aguarda página estabilizar com timeout moderado
    try:
        await asyncio.wait_for(
            page.wait_for_load_state("load", timeout=10000),
            timeout=10.0
        )
        await asyncio.sleep(1.0)  # Aguarda elementos dinâmicos carregarem (aumentado)
    except (asyncio.TimeoutError, Exception):
        logger.debug("Timeout no wait_for_load_state, continuando...")
        await asyncio.sleep(1.0)
    
    logger.debug("Página pronta para extração de dados")
    
    # URL final (canonical)
    final_url = page.url
    try:
        canon = await asyncio.wait_for(
            page.get_attribute("link[rel='canonical']", "href"),
            timeout=2.0
        )
        if canon:
            final_url = canon
    except (asyncio.TimeoutError, Exception):
        pass
    
    # TÍTULO: Extração rápida com timeout
    logger.debug("Extraindo título...")
    title = ""
    try:
        title = await asyncio.wait_for(page.title(), timeout=3.0) or ""
        logger.debug(f"Título extraído: {title[:50]}...")
    except (asyncio.TimeoutError, Exception) as e:
        logger.debug(f"Erro ao extrair título (ignorando): {e}")
    
    # PREÇO: Busca com múltiplos seletores
    logger.debug("Extraindo preço...")
    price = None
    
    # Lista de seletores para tentar (do mais específico ao mais genérico)
    price_selectors = [
        "[data-testid='vip-price']",
        ".ui-pdp-price__second-line .andes-money-amount__fraction",
        ".ui-pdp-price .andes-money-amount__fraction",
        "span.andes-money-amount__fraction",
        ".price-tag-fraction",
    ]
    
    for selector in price_selectors:
        try:
            logger.debug(f"Tentando seletor de preço: {selector}")
            # Aguarda o elemento aparecer
            await asyncio.wait_for(
                page.wait_for_selector(selector, timeout=4000, state="visible"),
                timeout=4.5
            )
            await asyncio.sleep(0.3)  # Aguarda renderização
            price_text = await asyncio.wait_for(
                page.locator(selector).first.text_content(timeout=3000),
                timeout=3.5
            )
            if price_text:
                logger.debug(f"Texto do preço bruto encontrado: '{price_text}'")
                price = _parse_money(price_text)
                if price:
                    logger.info(f"✅ Preço encontrado com seletor '{selector}': R$ {price}")
                    break
                else:
                    logger.debug(f"Falha ao parsear preço: '{price_text}'")
        except (asyncio.TimeoutError, Exception) as e:
            logger.debug(f"Seletor '{selector}' falhou: {e}")
            continue
    
    if not price:
        logger.warning(f"⚠️ Nenhum preço encontrado para {url}")
    
    # IMAGEM: Busca rápida em meta tags (og:image) com timeout
    logger.debug("Extraindo imagem...")
    image_url: str | None = None
    try:
        # Tenta primeiro og:image (mais rápido)
        og_image = await asyncio.wait_for(
            page.get_attribute("meta[property='og:image']", "content"),
            timeout=2.0
        )
        if og_image:
            image_url = og_image
            logger.debug(f"Imagem encontrada via og:image: {image_url[:50]}...")
    except (asyncio.TimeoutError, Exception):
        # Fallback: primeira imagem em schema.org
        try:
            img_sel = await asyncio.wait_for(
                page.locator("img[itemprop='image']").first.get_attribute("src"),
                timeout=2.0
            )
            if img_sel:
                image_url = img_sel
                logger.debug(f"Imagem encontrada via itemprop: {image_url[:50]}...")
        except (asyncio.TimeoutError, Exception):
            logger.debug("Imagem não encontrada (ignorando)")
    
    # Monta objeto Product com dados mínimos
    id_meli = extract_meli_id(final_url or url)
    logger.debug(f"✅ Extração concluída. ID: {id_meli}, Título: {title[:50]}")
    
    return Product(
        id_meli=id_meli,
        title=title.strip() or id_meli,
        url=final_url or url,  # type: ignore[arg-type]
        image_url=image_url,  # type: ignore[arg-type]
        price=price,
        original_price=None,  # Não essencial - removido
        discount_pct=None,  # Não essencial - removido
        rating=None,  # Não essencial - removido
        reviews=None,  # Não essencial - removido
        free_shipping=False,  # Não essencial - removido
        in_stock=None,  # Não essencial - removido
    )


def _parse_money(text: str) -> Optional[float]:
    """Parse texto de preço em formato brasileiro (ex: R$ 1.234,56)"""
    if not text:
        return None
    
    # Remove espaços e caracteres não-numéricos exceto vírgula e ponto
    nums = re.sub(r"[^0-9,\.]", "", text.strip())
    
    if not nums:
        return None
    
    # Formato brasileiro: 1.234,56 -> converte para 1234.56
    # Se tem vírgula, assume que é o separador decimal
    if "," in nums:
        # Remove pontos (separador de milhar) e substitui vírgula por ponto
        nums = nums.replace(".", "").replace(",", ".")
    # Se tem apenas pontos e mais de um, o último é decimal
    elif nums.count(".") > 1:
        parts = nums.rsplit(".", 1)
        nums = parts[0].replace(".", "") + "." + parts[1]
    
    try:
        value = float(nums)
        logger.debug(f"_parse_money: '{text}' -> {value}")
        return value
    except (ValueError, TypeError) as e:
        logger.debug(f"_parse_money: Falha ao converter '{text}' (nums='{nums}'): {e}")
        return None


async def download_image(url: str, dest: Path) -> Path | None:
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            r = await client.get(url)
            r.raise_for_status()
            dest.write_bytes(r.content)
            return dest
    except Exception as e:  # noqa: BLE001
        logger.debug(f"Falha ao baixar imagem: {e}")
        return None


def build_short_link_from_id(url: str) -> Optional[str]:
    """Tenta construir um link curto limpo a partir da URL do produto.
    
    Como fallback quando o botão Compartilhar não funciona, esta função:
    1. Remove parâmetros de tracking da URL original
    2. Limpa fragmentos (#)
    3. Retorna URL canônica do produto
    
    Args:
        url: URL completa do produto no Mercado Livre
        
    Returns:
        URL limpa sem parâmetros de tracking, ou None se não conseguir processar
    """
    try:
        # Remove fragmentos (#)
        clean_url = url.split("#")[0]
        
        # Remove parâmetros de tracking comuns do ML
        # Exemplos: polycard_client, tracking_id, wid, sid
        if "?" in clean_url:
            base_url, query_string = clean_url.split("?", 1)
            # Parâmetros a remover
            tracking_params = [
                "polycard_client",
                "tracking_id",
                "wid",
                "sid",
                "position",
                "search_location",
            ]
            
            # Processar query string e filtrar parâmetros de tracking
            params = query_string.split("&")
            filtered_params = [
                p for p in params 
                if not any(tp in p for tp in tracking_params)
            ]
            
            if filtered_params:
                clean_url = f"{base_url}?{'&'.join(filtered_params)}"
            else:
                clean_url = base_url
        
        # Garantir que é uma URL válida
        if clean_url.startswith("http"):
            logger.debug(f"Link limpo gerado: {clean_url[:60]}...")
            return clean_url
        
        return None
    except Exception as e:
        logger.debug(f"Erro ao construir link curto: {e}")
        return None


def build_affiliate_link(settings: Settings, source_url: str) -> str:
    # MVP: sem programa; adiciona UTMs simples
    utm = (
        f"utm_source={settings.affiliate.utm_source}&"
        f"utm_medium={settings.affiliate.utm_medium}&"
        f"utm_campaign={settings.affiliate.utm_campaign_prefix}{_today()}"
    )
    sep = "&" if ("?" in source_url) else "?"
    return f"{source_url}{sep}{utm}"


def passes_filters(settings: Settings, product: Product) -> bool:
    if settings.min_rating and (product.rating or 0.0) < settings.min_rating:
        return False
    if settings.min_discount and (product.discount_pct or 0.0) < settings.min_discount:
        return False
    if settings.price_min is not None and (product.price or 0.0) < settings.price_min:
        return False
    if settings.price_max is not None and (product.price or 0.0) > settings.price_max:
        return False
    return True


def _today() -> str:
    from datetime import datetime

    return datetime.utcnow().strftime("%Y%m")
