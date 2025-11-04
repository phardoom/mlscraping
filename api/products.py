"""Endpoints relacionados a produtos, exportação e categorias."""

from fastapi import APIRouter

from api.schemas import ExportResponse, ProductResponse
from config import MELI_CATEGORIES, get_settings
from store import Repo


def create_router() -> APIRouter:
    """Cria router com endpoints de produtos."""
    router = APIRouter()

    @router.get("/products", response_model=list[ProductResponse])
    async def list_products(limit: int = 50) -> list[ProductResponse]:
        """Lista produtos extraídos."""
        settings = get_settings()
        repo = Repo(settings.db_path)
        products = repo.fetch_products_with_links(limit=limit)
        return [ProductResponse(**p) for p in products]

    @router.get("/export", response_model=ExportResponse)
    async def export_now() -> ExportResponse:
        """Exporta produtos em CSV, JSON e TXT."""
        settings = get_settings()
        repo = Repo(settings.db_path)
        csv_p, json_p, txt_p = repo.export_csv_json_messages(settings.out_dir)
        return ExportResponse(csv=str(csv_p), json=str(json_p), txt=str(txt_p))

    @router.get("/categories")
    async def list_categories() -> list[str]:
        """Retorna lista de categorias do Mercado Livre."""
        return MELI_CATEGORIES

    return router
