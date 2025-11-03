from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

from browser import BrowserSession
from config import Settings, get_settings
from logging_setup import setup_logging
from store import Repo
from runner import run_scrape


app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command()
def login() -> None:
    """Abre o navegador para que você faça login no Mercado Livre."""

    setup_logging()
    settings = get_settings()

    async def _run() -> None:
        s = BrowserSession(settings)
        await s.start(headless=False)
        try:
            await s.login_flow()
        finally:
            await s.stop()

    asyncio.run(_run())
    logger.success("Login concluído e sessão salva.")


@app.command()
def scrape(
    url: str = typer.Option(..., "--url", help="URL da listagem (ex.: Mais vendidos)"),
    max_items: int = typer.Option(50, "--max-items", help="Quantidade máxima de itens"),
    min_discount: float = typer.Option(0.0, "--min-discount", help="Desconto mínimo (%)"),
    min_rating: float = typer.Option(0.0, "--min-rating", help="Rating mínimo (0-5)"),
    price_min: Optional[float] = typer.Option(None, "--price-min", help="Preço mínimo"),
    price_max: Optional[float] = typer.Option(None, "--price-max", help="Preço máximo"),
    headless: Optional[bool] = typer.Option(None, "--headless/--headful", help="Rodar sem/ com UI do navegador"),
    debug: bool = typer.Option(False, "--debug", help="Salva screenshots/HTML para diagnóstico"),
) -> None:
    """Coleta produtos da listagem, abre cada página, extrai link de compartilhamento e exporta arquivos."""

    setup_logging()
    settings = get_settings()
    settings.max_items = max_items
    settings.min_discount = min_discount
    settings.min_rating = min_rating
    settings.price_min = price_min
    settings.price_max = price_max
    if headless is not None:
        settings.headless = headless
    if debug:
        # habilita logs detalhados
        logger.level("DEBUG")

    repo = Repo(settings.db_path)
    repo.init()

    async def _run() -> None:
        async def progress(ev: dict) -> None:
            t = ev.get("type")
            if t == "item_begin":
                logger.info(f"[{ev.get('index')}/{ev.get('total')}] {ev.get('url')}")
            elif t == "item_saved":
                logger.info(f"Salvo: {ev.get('title')}")
            elif t == "item_filtered":
                logger.info("Filtrado pelos critérios.")
            elif t == "list_collected":
                logger.info(f"Coletou {ev.get('count')} URLs na listagem")

        await run_scrape(settings, repo, url=url, max_items=settings.max_items, progress=progress)

    asyncio.run(_run())
    logger.success("Scraping finalizado.")


@app.command()
def export() -> None:
    """Exporta CSV, JSON e messages.txt a partir do banco atual."""

    setup_logging()
    settings = get_settings()
    repo = Repo(settings.db_path)
    repo.init()
    repo.export_csv_json_messages(settings.out_dir)
    logger.success("Export concluído.")


@app.command("sync-images")
def sync_images() -> None:
    """Baixa imagens ausentes para os produtos no banco."""

    setup_logging()
    settings = get_settings()
    repo = Repo(settings.db_path)
    products = repo.iter_products()
    missing = 0
    async def _run() -> None:
        nonlocal missing
        for p in products:
            img_url = p.get("image_url")
            if not img_url:
                continue
            img_path = settings.images_dir / f"{p['id_meli']}.jpg"
            if not img_path.exists():
                await download_image(img_url, img_path)
                missing += 1

    asyncio.run(_run())
    logger.success(f"Imagens sincronizadas. Novas baixadas: {missing}")


if __name__ == "__main__":
    app()
