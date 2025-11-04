"""Endpoints relacionados ao WhatsApp."""

import asyncio
import json

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException
from loguru import logger

from config import get_settings
from models import MessageTemplate, Product, WhatsAppConfig
from store import Repo
from whatsapp import EvolutionAPIClient

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


@router.post("/config")
async def save_whatsapp_config(payload: dict) -> dict:
    """Salva configuração da Evolution API."""
    settings = get_settings()
    config = WhatsAppConfig(
        base_url=payload.get("base_url", ""),
        api_key=payload.get("api_key", ""),
        instance_name=payload.get("instance_name", ""),
    )
    
    # Salva em arquivo JSON
    settings.whatsapp_config_path.parent.mkdir(parents=True, exist_ok=True)
    with settings.whatsapp_config_path.open("w", encoding="utf-8") as f:
        json.dump(config.model_dump(), f, indent=2)
    
    logger.info(f"Configuração WhatsApp salva: {config.instance_name}")
    return {"ok": True}


@router.get("/config")
async def get_whatsapp_config() -> dict:
    """Retorna configuração salva da Evolution API."""
    settings = get_settings()
    if not settings.whatsapp_config_path.exists():
        return {"base_url": "", "api_key": "", "instance_name": ""}
    
    with settings.whatsapp_config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/groups")
async def list_whatsapp_groups() -> list[dict]:
    """Lista grupos disponíveis na Evolution API."""
    settings = get_settings()
    if not settings.whatsapp_config_path.exists():
        raise HTTPException(400, "Configuração WhatsApp não encontrada. Configure primeiro em /whatsapp/config")
    
    with settings.whatsapp_config_path.open("r", encoding="utf-8") as f:
        config_data = json.load(f)
    
    config = WhatsAppConfig(**config_data)
    client = EvolutionAPIClient(config)
    try:
        groups = await client.list_groups()
        return [{"group_id": g.group_id, "name": g.name} for g in groups]
    except httpx.HTTPStatusError as e:
        error_msg = f"Erro ao conectar com Evolution API: {e.response.status_code}"
        if e.response.status_code == 401:
            error_msg += " - Verifique se a API Key está correta"
        elif e.response.status_code == 404:
            error_msg += " - Verifique se o endpoint/instância está correta"
        logger.error(f"{error_msg}: {e.response.text[:200]}")
        raise HTTPException(status_code=e.response.status_code, detail=error_msg)
    except Exception as e:
        error_msg = f"Erro ao listar grupos: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/debug")
async def debug_whatsapp() -> dict:
    """Endpoint de debug para inspecionar resposta da Evolution API."""
    settings = get_settings()
    if not settings.whatsapp_config_path.exists():
        raise HTTPException(400, "Configuração WhatsApp não encontrada")
    
    with settings.whatsapp_config_path.open("r", encoding="utf-8") as f:
        config_data = json.load(f)
    
    config = WhatsAppConfig(**config_data)
    # Remove trailing slash para evitar double slash
    base_url_clean = config.base_url.rstrip("/")
    url = f"{base_url_clean}/group/fetchAllGroups/{config.instance_name}?getParticipants=false"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                headers={"apikey": config.api_key, "Content-Type": "application/json"},
            )
            return {
                "status_code": response.status_code,
                "url": url,
                "raw_response": response.text,
                "headers": dict(response.headers),
                "api_key_prefix": config.api_key[:10] + "..." if len(config.api_key) > 10 else config.api_key,
                "note": "Verifique se a API_KEY corresponde à AUTHENTICATION_API_KEY do Portainer (ac4525fdcb...)"
            }
    except Exception as e:
        return {"error": str(e), "url": url}


@router.post("/test-endpoint")
async def test_endpoint(payload: dict) -> dict:
    """Testa um endpoint específico da Evolution API."""
    url = payload.get("url", "")
    api_key = payload.get("api_key", "")
    
    if not url or not api_key:
        raise HTTPException(400, "url e api_key são obrigatórios")
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                url,
                headers={"apikey": api_key, "Content-Type": "application/json"},
            )
            return {
                "status_code": response.status_code,
                "url": url,
                "response": response.text[:500],
            }
    except Exception as e:
        return {"error": str(e), "url": url, "status_code": 500}


@router.post("/disable-groups-ignore")
async def disable_groups_ignore() -> dict:
    """Desativa groupsIgnore na instância."""
    settings = get_settings()
    if not settings.whatsapp_config_path.exists():
        raise HTTPException(400, "Configuração WhatsApp não encontrada")
    
    with settings.whatsapp_config_path.open("r", encoding="utf-8") as f:
        config_data = json.load(f)
    
    config = WhatsAppConfig(**config_data)
    # Remove trailing slash para evitar double slash
    base_url_clean = config.base_url.rstrip("/")
    url = f"{base_url_clean}/settings/set/{config.instance_name}"
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers={"apikey": config.api_key, "Content-Type": "application/json"},
                json={"groupsIgnore": False}
            )
            return {
                "status_code": response.status_code,
                "url": url,
                "response": response.text,
            }
    except Exception as e:
        return {"error": str(e), "url": url}


@router.post("/send")
async def send_whatsapp_messages(payload: dict, background_tasks: BackgroundTasks) -> dict:
    """Envia produtos para grupos do WhatsApp."""
    product_ids = payload.get("product_ids", [])
    group_ids = payload.get("group_ids", [])
    template_text = payload.get("template", "")
    
    if not product_ids:
        raise HTTPException(400, "product_ids é obrigatório")
    if not group_ids:
        raise HTTPException(400, "group_ids é obrigatório")
    if not template_text:
        raise HTTPException(400, "template é obrigatório")
    
    # Carrega configuração
    settings = get_settings()
    if not settings.whatsapp_config_path.exists():
        raise HTTPException(400, "Configuração WhatsApp não encontrada")
    
    with settings.whatsapp_config_path.open("r", encoding="utf-8") as f:
        config_data = json.load(f)
    
    config = WhatsAppConfig(**config_data)
    
    # Busca produtos do banco
    repo = Repo(settings.db_path)
    all_products = repo.fetch_products_with_links(limit=1000)
    products_dict = {p["id_meli"]: p for p in all_products}
    
    # Filtra produtos solicitados e cria dict de links compartilhados
    selected_products = []
    product_share_links = {}
    for pid in product_ids:
        if pid in products_dict:
            p_data = products_dict[pid]
            # Converte dict para Product
            p = Product(
                id_meli=p_data["id_meli"],
                title=p_data["title"],
                url=p_data["url"],
                image_url=p_data.get("image_url"),
                price=p_data.get("price"),
                category=p_data.get("category"),
            )
            selected_products.append(p)
            # Guarda link compartilhado se disponível
            if p_data.get("link_compartilhado"):
                product_share_links[pid] = p_data["link_compartilhado"]
    
    if not selected_products:
        raise HTTPException(400, "Nenhum produto válido encontrado para os IDs fornecidos")
    
    template = MessageTemplate(template_text=template_text)
    
    # Envia em background
    async def send_task() -> None:
        # Cria lista de produtos com links compartilhados
        products_with_links = []
        for p in selected_products:
            share_link = product_share_links.get(p.id_meli)
            products_with_links.append((p, share_link))
        
        # Envia usando função customizada
        client = EvolutionAPIClient(config)
        stats = {"sent": 0, "failed": 0}
        
        for product, share_link in products_with_links:
            message_text = client.format_product_message(product, template, share_link)
            for group_id in group_ids:
                success = await client.send_text_message(group_id, message_text)
                if success:
                    stats["sent"] += 1
                else:
                    stats["failed"] += 1
                await asyncio.sleep(2.0)  # Delay entre mensagens
        
        logger.info(f"Envio WhatsApp concluído: {stats}")
    
    background_tasks.add_task(send_task)
    
    return {"ok": True, "message": f"Enviando {len(selected_products)} produtos para {len(group_ids)} grupos"}
