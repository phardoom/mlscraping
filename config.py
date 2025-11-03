from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AffiliateConfig(BaseModel):
    """Configuração para construção de links de afiliado.

    MVP: sem deep-link específico. Mantém UTMs opcionais e permite troca futura.
    """

    strategy: str = Field(
        default="none", description="Estratégia de construção do link (none/query_param/pattern)."
    )
    tag: Optional[str] = Field(default=None, description="Identificador/aff_id/tag do afiliado.")
    base_url: Optional[str] = Field(default=None, description="Base para padrões do programa, se houver.")
    query_key: Optional[str] = Field(default=None, description="Nome do parâmetro de query, se usar query_param.")
    utm_source: str = "whatsapp"
    utm_medium: str = "group"
    utm_campaign_prefix: str = "ofertas_"


# Lista de categorias do Mercado Livre
MELI_CATEGORIES = [
    "Acessórios para Veículos",
    "Agro",
    "Alimentos e Bebidas",
    "Antiguidades e Coleções",
    "Arte, Papelaria e Armarinho",
    "Bebês",
    "Beleza e Cuidado Pessoal",
    "Brinquedos e Hobbies",
    "Calçados, Roupas e Bolsas",
    "Casa, Móveis e Decoração",
    "Celulares e Telefones",
    "Construção",
    "Câmeras e Acessórios",
    "Eletrodomésticos",
    "Eletrônicos, Áudio e Vídeo",
    "Esportes e Fitness",
    "Ferramentas",
    "Festas e Lembrancinhas",
    "Games",
    "Indústria e Comércio",
    "Informática",
    "Instrumentos Musicais",
    "Joias e Relógios",
    "Livros, Revistas e Comics",
    "Música, Filmes e Seriados",
    "Pet Shop",
    "Saúde",
    "Serviços",
    "Outros",
]


class Settings(BaseSettings):
    """Definições gerais da aplicação."""

    # Execução
    headless: bool = True
    max_items: int = 50
    rate_limit_ms: int = 800
    nav_timeout_ms: int = 120000  # 2 minutos - aumentado para evitar timeouts em páginas lentas

    # Diretórios
    out_dir: Path = Path("data/out")
    images_dir: Path = Path("data/images")
    state_path: Path = Path("data/state/storage_state.json")
    db_path: Path = Path("data/app.db")
    whatsapp_config_path: Path = Path("data/whatsapp_config.json")
    template_path: Path = Path("data/message_template.json")

    # Afiliado/UTM
    affiliate: AffiliateConfig = Field(default_factory=AffiliateConfig)

    # Filtros básicos
    min_discount: float = 0.0
    min_rating: float = 0.0
    price_min: float | None = None
    price_max: float | None = None

    # Evolution API (opcional, pode ser configurado via interface)
    evolution_api_url: Optional[str] = None
    evolution_api_key: Optional[str] = None
    evolution_instance_name: Optional[str] = None

    model_config = SettingsConfigDict(
        env_prefix="ML_",
        env_file=".env",
        case_sensitive=False,
    )

    @field_validator("out_dir", "images_dir", "state_path", "db_path")
    @classmethod
    def _ensure_path(cls, v: Path) -> Path:  # type: ignore[override]
        # Não cria diretórios aqui; criação é feita em runtime quando necessário
        return v


def get_settings() -> Settings:
    """Factory de Settings para import fácil."""

    return Settings()  # type: ignore[call-arg]
