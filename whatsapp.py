from __future__ import annotations

import asyncio
from typing import Optional

import httpx
from loguru import logger

from models import MessageTemplate, Product, WhatsAppConfig, WhatsAppGroup


class EvolutionAPIClient:
    """Cliente para interagir com Evolution API."""

    def __init__(self, config: WhatsAppConfig) -> None:
        self.config = config
        self.base_url = config.base_url.rstrip("/")  # Remove trailing slash
        self.api_key = config.api_key
        self.instance_name = config.instance_name

    def _get_headers(self) -> dict[str, str]:
        """Retorna headers padrão para requisições."""
        return {
            "Content-Type": "application/json",
            "apikey": self.api_key,
        }

    async def send_text_message(self, group_id: str, text: str) -> bool:
        """Envia mensagem de texto para um grupo."""
        url = f"{self.base_url}/message/sendText/{self.instance_name}"
        
        payload = {
            "number": group_id,
            "text": text,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=self._get_headers(),
                )
                response.raise_for_status()
                result = response.json()
                
                if result.get("status") == "success" or result.get("messageId"):
                    logger.info(f"✅ Mensagem enviada para grupo {group_id}")
                    return True
                else:
                    logger.warning(f"⚠️ Resposta inesperada: {result}")
                    return False
        except httpx.HTTPStatusError as e:
            logger.error(f"❌ Erro HTTP ao enviar mensagem: {e.response.status_code} - {e.response.text}")
            return False
        except Exception as e:
            logger.error(f"❌ Erro ao enviar mensagem para {group_id}: {e}")
            return False

    async def list_groups(self) -> list[WhatsAppGroup]:
        """Lista grupos disponíveis - tenta múltiplos endpoints da Evolution API.
        
        Raises:
            httpx.HTTPStatusError: Se todos os endpoints retornarem erro HTTP.
            ValueError: Se nenhum endpoint retornar grupos válidos.
        """
        
        # Primeiro, verifica se a instância existe e está conectada
        instance_check_url = f"{self.base_url}/instance/connectionState/{self.instance_name}"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                check_response = await client.get(instance_check_url, headers=self._get_headers())
                if check_response.status_code == 200:
                    instance_state = check_response.json()
                    logger.debug(f"Estado da instância: {instance_state}")
                    state = instance_state.get("state") if isinstance(instance_state, dict) else None
                    if state not in ["open", "connected"]:
                        logger.warning(f"Instância não está conectada (estado: {state})")
                else:
                    logger.warning(f"Não foi possível verificar estado da instância: {check_response.status_code}")
        except Exception as e:
            logger.debug(f"Erro ao verificar estado da instância: {e}")
        
        # Lista de endpoints alternativos da Evolution API
        # O endpoint fetchAllGroups requer o parâmetro getParticipants na query string
        alternative_endpoints = [
            f"{self.base_url}/group/fetchAllGroups/{self.instance_name}?getParticipants=true",
            f"{self.base_url}/group/fetchAllGroups/{self.instance_name}?getParticipants=false",
            f"{self.base_url}/group/allGroups/{self.instance_name}",
            f"{self.base_url}/{self.instance_name}/group",
            f"{self.base_url}/chat/fetchAllGroups/{self.instance_name}",
            f"{self.base_url}/chat/fetchGroups/{self.instance_name}",
            f"{self.base_url}/group/{self.instance_name}",
            f"{self.base_url}/{self.instance_name}/groups",
        ]
        
        headers = self._get_headers()
        last_error: Exception | None = None
        
        # Tenta cada endpoint até encontrar um que funcione
        for url in alternative_endpoints:
            logger.debug(f"Tentando endpoint: {url}")
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.get(url, headers=headers)
                    logger.debug(f"Response status: {response.status_code}")
                    # Verifica se status é 2xx (sucesso)
                    if response.status_code >= 200 and response.status_code < 300:
                        # Tenta processar resposta de sucesso
                        data = response.json()
                        logger.debug(f"Response data type: {type(data)}, content: {str(data)[:200]}")
                        
                        groups = []
                        groups_data = []
                        
                        # Tenta vários formatos de resposta
                        if isinstance(data, dict):
                            # Procura por diferentes chaves comuns
                            if "response" in data:
                                groups_data = data["response"] if isinstance(data["response"], list) else []
                            elif "groups" in data:
                                groups_data = data["groups"] if isinstance(data["groups"], list) else []
                            elif "data" in data:
                                groups_data = data["data"] if isinstance(data["data"], list) else []
                            elif "result" in data:
                                groups_data = data["result"] if isinstance(data["result"], list) else []
                        elif isinstance(data, list):
                            groups_data = data
                        else:
                            logger.warning(f"Formato de resposta inesperado: {type(data)}")
                            continue

                        for group in groups_data:
                            if isinstance(group, dict):
                                # Tenta vários campos para ID
                                group_id = (
                                    group.get("id") or 
                                    group.get("group_id") or 
                                    group.get("jid") or 
                                    group.get("_serialized") or
                                    ""
                                )
                                # Tenta vários campos para nome
                                name = (
                                    group.get("subject") or 
                                    group.get("name") or 
                                    group.get("title") or
                                    group_id or
                                    "Sem nome"
                                )
                                if group_id:  # Só adiciona se tiver ID
                                    groups.append(WhatsAppGroup(group_id=group_id, name=name))
                                else:
                                    logger.debug(f"Grupo sem ID ignorado: {group}")

                        if groups:
                            logger.info(f"✅ {len(groups)} grupos encontrados via {url}")
                            return groups
                        else:
                            logger.debug(f"Nenhum grupo encontrado em {url}")
                    else:
                        # Status não é 2xx, continua para próximo endpoint
                        logger.debug(f"Status {response.status_code} não é sucesso, tentando próximo endpoint...")
                        last_error = httpx.HTTPStatusError(f"Status {response.status_code}", request=response.request, response=response)
                        continue
                        
            except httpx.HTTPStatusError as e:
                logger.debug(f"HTTP {e.response.status_code} em {url}: {e.response.text[:100]}")
                last_error = e
                continue
            except Exception as e:
                logger.debug(f"Erro em {url}: {e}")
                last_error = e
                continue
        
        # Se nenhum endpoint funcionou, lança exceção
        if last_error:
            logger.error(f"❌ Nenhum endpoint válido encontrado para listar grupos. Último erro: {last_error}")
            raise last_error
        else:
            raise ValueError("Nenhum endpoint retornou grupos válidos após tentar todos os endpoints")

    def format_product_message(self, product: Product, template: MessageTemplate, share_link: Optional[str] = None) -> str:
        """Formata mensagem do produto usando o template."""
        text = template.template_text
        
        # Usa link compartilhado se fornecido, senão usa URL do produto
        link = share_link if share_link else str(product.url)
        
        # Substitui placeholders
        replacements = {
            "{titulo}": product.title,
            "{preco}": f"R$ {product.price:.2f}".replace(".", ",") if product.price else "N/A",
            "{link}": link,
            "{desconto}": f"{product.discount_pct:.0f}% OFF" if product.discount_pct else "",
        }
        
        for placeholder, value in replacements.items():
            text = text.replace(placeholder, str(value))
        
        return text


async def send_products_to_whatsapp(
    products: list[Product],
    groups: list[str],
    template: MessageTemplate,
    config: WhatsAppConfig,
    delay_seconds: float = 2.0,
) -> dict[str, int]:
    """Envia produtos para grupos selecionados.
    
    Args:
        products: Lista de produtos para enviar
        groups: Lista de IDs de grupos
        template: Template de mensagem
        config: Configuração da Evolution API
        delay_seconds: Delay entre mensagens (padrão 2s)
    
    Returns:
        Dict com estatísticas: {"sent": X, "failed": Y}
    """
    client = EvolutionAPIClient(config)
    stats = {"sent": 0, "failed": 0}
    
    total_messages = len(products) * len(groups)
    logger.info(f"📤 Enviando {len(products)} produtos para {len(groups)} grupos ({total_messages} mensagens)")
    
    for product in products:
        message_text = client.format_product_message(product, template)
        
        for group_id in groups:
            success = await client.send_text_message(group_id, message_text)
            
            if success:
                stats["sent"] += 1
            else:
                stats["failed"] += 1
            
            # Delay entre mensagens para evitar rate limit
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)
    
    logger.info(f"✅ Envio concluído: {stats['sent']} enviadas, {stats['failed']} falhas")
    return stats

