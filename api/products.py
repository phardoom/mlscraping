"""Endpoints relacionados a produtos, exportação e categorias."""

from fastapi import APIRouter

from config import MELI_CATEGORIES, get_settings
from store import Repo


def create_router() -> APIRouter:
    """Cria router com endpoints de produtos."""
    router = APIRouter()

    @router.get("/products")
    async def list_products(limit: int = 50) -> list[dict]:
        settings = get_settings()
        repo = Repo(settings.db_path)
        return repo.fetch_products_with_links(limit=limit)

    @router.get("/export")
    async def export_now() -> dict:
        settings = get_settings()
        repo = Repo(settings.db_path)
        csv_p, json_p, txt_p = repo.export_csv_json_messages(settings.out_dir)
        return {"csv": str(csv_p), "json": str(json_p), "txt": str(txt_p)}

    @router.get("/categories")
    async def list_categories() -> list[str]:
        """Retorna lista de categorias do Mercado Livre."""
        return MELI_CATEGORIES

    return router
