from __future__ import annotations

from typing import Optional

from models import Product


def format_whatsapp_message(product: Product, affiliate_url: str) -> str:
    """Cria uma mensagem curta e direta para WhatsApp."""

    preco = f"R${product.price:.2f}" if product.price is not None else "Preço indisponível"
    desconto = (
        f" ({product.discount_pct:.0f}% OFF)" if product.discount_pct is not None and product.discount_pct > 0 else ""
    )
    rating = f" | ⭐ {product.rating:.1f}" if product.rating is not None else ""
    frete = " | Frete grátis" if product.free_shipping else ""
    title = product.title.strip()
    return f"🔥 {title} — {preco}{desconto}{rating}{frete}\n{affiliate_url}"

