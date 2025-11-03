from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, HttpUrl


class Product(BaseModel):
    """Representa um produto do Mercado Livre."""

    id_meli: str
    title: str
    url: HttpUrl
    image_url: Optional[HttpUrl] = None
    price: Optional[float] = None
    original_price: Optional[float] = None
    discount_pct: Optional[float] = None
    rating: Optional[float] = None
    reviews: Optional[int] = None
    free_shipping: bool = False
    seller: Optional[str] = None
    category: Optional[str] = None
    in_stock: Optional[bool] = None
    collected_at: datetime = Field(default_factory=datetime.utcnow)


class AffiliateLink(BaseModel):
    source_url: HttpUrl
    final_url: HttpUrl
    short_url: Optional[HttpUrl] = None


class Message(BaseModel):
    product_id: str
    text: str
    image_path: Optional[str] = None


class WhatsAppConfig(BaseModel):
    """Configuração da Evolution API."""
    base_url: str
    api_key: str
    instance_name: str


class WhatsAppGroup(BaseModel):
    """Grupo do WhatsApp."""
    group_id: str
    name: str


class MessageTemplate(BaseModel):
    """Template de mensagem com placeholders."""
    template_text: str
    placeholders: list[str] = Field(
        default=["{titulo}", "{preco}", "{link}", "{desconto}"],
        description="Placeholders disponíveis no template"
    )

