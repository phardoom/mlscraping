"""Endpoints relacionados a categorias."""
from fastapi import APIRouter

from config import MELI_CATEGORIES

router = APIRouter(tags=["categories"])


@router.get("/categories")
async def list_categories() -> list[str]:
    """Retorna lista de categorias do Mercado Livre."""
    return MELI_CATEGORIES
