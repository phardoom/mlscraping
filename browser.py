from __future__ import annotations

import asyncio
from pathlib import Path
from typing import AsyncIterator

from loguru import logger
from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from config import Settings


class BrowserSession:
    """Gerencia o navegador Playwright com estado persistido."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._pw: Playwright | None = None

    async def __aenter__(self) -> "BrowserSession":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        await self.stop()

    async def start(self, headless: bool | None = None) -> None:
        headless = self.settings.headless if headless is None else headless
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=headless)

        storage_state: str | None = None
        if self.settings.state_path.exists():
            storage_state = str(self.settings.state_path)
            logger.debug(f"Usando storage_state: {storage_state}")

        self._context = await self._browser.new_context(
            storage_state=storage_state,
            permissions=["clipboard-read", "clipboard-write"],
            viewport={"width": 1460, "height": 900},
            # Bloqueia recursos desnecessários para acelerar carregamento
            ignore_https_errors=True,
            # Desabilita JavaScript de tracking/analytics (opcional - pode quebrar alguns sites)
            # java_script_enabled=True,  # Mantém JS habilitado pois o site precisa
        )
        
        # Bloqueia apenas recursos realmente desnecessários para acelerar
        async def route_handler(route):
            """Bloqueia recursos desnecessários para acelerar."""
            resource_type = route.request.resource_type
            url = route.request.url
            
            # Bloqueia apenas recursos pesados que não são essenciais para extração
            blocked_types = [
                "media",  # Bloqueia vídeos/áudio (não necessários)
            ]
            
            # Bloqueia fontes de terceiros, mas permite do próprio site
            if resource_type == "font" and "mercadolivre.com.br" not in url:
                await route.abort()
            # Bloqueia outros recursos pesados de terceiros
            elif resource_type in blocked_types:
                await route.abort()
            else:
                await route.continue_()
        
        # Aplica bloqueio sempre (acelera tanto headless quanto headful)
        await self._context.route("**/*", route_handler)

    async def stop(self) -> None:
        if self._context:
            # Salva storage_state para reuso
            if not self.settings.state_path.parent.exists():
                self.settings.state_path.parent.mkdir(parents=True, exist_ok=True)
            await self._context.storage_state(path=str(self.settings.state_path))

        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    async def new_page(self) -> Page:
        if not self._context:
            raise RuntimeError("Contexto Playwright não inicializado")
        page = await self._context.new_page()
        page.set_default_timeout(self.settings.nav_timeout_ms)
        return page

    async def login_flow(self) -> None:
        """Abre o site para que o usuário faça login manualmente e salva o estado."""

        page = await self.new_page()
        await page.goto("https://www.mercadolivre.com.br/")
        logger.info("Navegador aberto. Faça login na sua conta e depois volte ao terminal.")
        logger.info("Quando terminar o login, pressione ENTER no terminal para continuar…")
        # Espera pelo ENTER no stdin
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: input())
        logger.info("Salvando estado da sessão…")
        # storage_state salvo em stop()


async def iter_pages(context: BrowserContext, urls: list[str]) -> AsyncIterator[Page]:
    """Abre páginas sequencialmente reutilizando o contexto."""

    for url in urls:
        page = await context.new_page()
        # Usa timeout padrão do Playwright (sem limite rígido)
        # O timeout específico é definido em cada operação individual
        yield page
        await page.close()
