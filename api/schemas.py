"""Schemas Pydantic para validação de dados da API."""

from pydantic import BaseModel, Field, HttpUrl, field_validator


class ScrapeStartRequest(BaseModel):
    """Schema para requisição de início de scraping."""
    url: str = Field(..., description="URL da listagem do Mercado Livre", min_length=1)
    max_items: int = Field(default=50, ge=1, le=500, description="Número máximo de itens a extrair")
    headless: bool = Field(default=True, description="Executar browser em modo headless")
    category: str | None = Field(default=None, description="Categoria opcional para filtro")

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Valida e limpa a URL."""
        url = v.strip()
        if url.startswith(":"):
            url = url[1:].strip()
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"URL inválida: {url}. Deve começar com http:// ou https://")
        return url


class ScrapeStartResponse(BaseModel):
    """Schema para resposta de início de scraping."""
    ok: bool = Field(..., description="Indica se o scraping foi iniciado com sucesso")


class ScrapeStopResponse(BaseModel):
    """Schema para resposta de parada de scraping."""
    ok: bool = Field(..., description="Indica se o scraping foi parado com sucesso")


class StatusResponse(BaseModel):
    """Schema para resposta de status."""
    running: bool = Field(..., description="Indica se o scraping está em execução")
    
    class Config:
        extra = "allow"  # Permite campos extras do last_status


class WhatsAppConfigRequest(BaseModel):
    """Schema para configuração do WhatsApp."""
    base_url: str = Field(..., description="URL base da Evolution API", min_length=1)
    api_key: str = Field(..., description="API Key da Evolution API", min_length=1)
    instance_name: str = Field(..., description="Nome da instância do WhatsApp", min_length=1)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        """Valida a URL base."""
        url = v.strip().rstrip("/")
        if not url.startswith(("http://", "https://")):
            raise ValueError("base_url deve começar com http:// ou https://")
        return url


class WhatsAppConfigResponse(BaseModel):
    """Schema para resposta de configuração do WhatsApp."""
    base_url: str
    api_key: str
    instance_name: str


class WhatsAppGroupResponse(BaseModel):
    """Schema para resposta de grupo do WhatsApp."""
    group_id: str = Field(..., description="ID do grupo")
    name: str = Field(..., description="Nome do grupo")


class WhatsAppSendRequest(BaseModel):
    """Schema para envio de mensagens WhatsApp."""
    product_ids: list[str] = Field(..., min_length=1, description="Lista de IDs dos produtos")
    group_ids: list[str] = Field(..., min_length=1, description="Lista de IDs dos grupos")
    template: str = Field(..., min_length=1, description="Template da mensagem")

    @field_validator("product_ids", "group_ids")
    @classmethod
    def validate_non_empty_list(cls, v: list[str]) -> list[str]:
        """Valida que a lista não está vazia."""
        if not v:
            raise ValueError("A lista não pode estar vazia")
        return v


class WhatsAppSendResponse(BaseModel):
    """Schema para resposta de envio WhatsApp."""
    ok: bool = Field(..., description="Indica se o envio foi iniciado")
    message: str = Field(..., description="Mensagem de confirmação")


class ProductResponse(BaseModel):
    """Schema para resposta de produto."""
    id_meli: str = Field(..., description="ID do produto no Mercado Livre")
    title: str = Field(..., description="Título do produto")
    url: str = Field(..., description="URL do produto")
    image_url: str | None = Field(default=None, description="URL da imagem")
    price: float | None = Field(default=None, description="Preço do produto")
    category: str | None = Field(default=None, description="Categoria do produto")
    discount_pct: float | None = Field(default=None, description="Percentual de desconto")
    link_compartilhado: str | None = Field(default=None, description="Link compartilhado do produto")


class ExportResponse(BaseModel):
    """Schema para resposta de exportação."""
    csv: str = Field(..., description="Caminho do arquivo CSV")
    json: str = Field(..., description="Caminho do arquivo JSON")
    txt: str = Field(..., description="Caminho do arquivo TXT")


class TestEndpointRequest(BaseModel):
    """Schema para teste de endpoint."""
    url: str = Field(..., description="URL do endpoint a testar", min_length=1)
    api_key: str = Field(..., description="API Key para autenticação", min_length=1)
