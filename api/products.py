"""Endpoints relacionados a produtos."""
from fastapi import APIRouter

from config import get_settings
from store import Repo

router = APIRouter(tags=["products"])


@router.get("/products")
async def list_products(limit: int = 50) -> list[dict]:
    """Lista produtos extraídos."""
    settings = get_settings()
    repo = Repo(settings.db_path)
    return repo.fetch_products_with_links(limit=limit)


@router.get("/export")
async def export_now() -> dict:
    """Exporta produtos para CSV, JSON e TXT."""
    settings = get_settings()
    repo = Repo(settings.db_path)
    csv_p, json_p, txt_p = repo.export_csv_json_messages(settings.out_dir)
    return {"csv": str(csv_p), "json": str(json_p), "txt": str(txt_p)}
