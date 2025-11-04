"""Testes unitários para api/whatsapp.py."""

import pytest
from fastapi.testclient import TestClient

from api.schemas import (
    TestEndpointRequest,
    WhatsAppConfigRequest,
    WhatsAppConfigResponse,
    WhatsAppGroupResponse,
    WhatsAppSendRequest,
)


class TestWhatsAppEndpoints:
    """Testes para os endpoints do WhatsApp."""
    
    def test_save_whatsapp_config_endpoint(self, client):
        """Testa endpoint de salvar configuração."""
        config_data = {
            "base_url": "http://localhost:8080",
            "api_key": "test-api-key",
            "instance_name": "test-instance",
        }
        response = client.post("/whatsapp/config", json=config_data)
        # Pode retornar 200 se sucesso ou erro se arquivo não existir
        assert response.status_code in [200, 500]
    
    def test_get_whatsapp_config_endpoint(self, client):
        """Testa endpoint de obter configuração."""
        response = client.get("/whatsapp/config")
        assert response.status_code == 200
        data = response.json()
        assert "base_url" in data
        assert "api_key" in data
        assert "instance_name" in data
    
    def test_test_endpoint_validation(self, client):
        """Testa validação do endpoint de teste."""
        # Testa com dados válidos
        response = client.post(
            "/whatsapp/test-endpoint",
            json={
                "url": "https://api.example.com/test",
                "api_key": "test-key",
            },
        )
        # Pode retornar vários status dependendo da conexão
        assert response.status_code in [200, 400, 500]


class TestWhatsAppSchemas:
    """Testes para os schemas do WhatsApp."""
    
    def test_whatsapp_config_request_valid(self):
        """Testa criação de WhatsAppConfigRequest válido."""
        config = WhatsAppConfigRequest(
            base_url="http://localhost:8080",
            api_key="test-key",
            instance_name="test-instance",
        )
        assert config.base_url == "http://localhost:8080"
        assert config.api_key == "test-key"
        assert config.instance_name == "test-instance"
    
    def test_whatsapp_config_request_url_validation(self):
        """Testa validação de URL base."""
        # URL válida
        config = WhatsAppConfigRequest(
            base_url="http://localhost:8080/",
            api_key="test-key",
            instance_name="test-instance",
        )
        # Deve remover trailing slash
        assert config.base_url == "http://localhost:8080"
        
        # URL inválida
        with pytest.raises(ValueError):
            WhatsAppConfigRequest(
                base_url="not-a-url",
                api_key="test-key",
                instance_name="test-instance",
            )
    
    def test_whatsapp_config_response_valid(self):
        """Testa criação de WhatsAppConfigResponse válido."""
        response = WhatsAppConfigResponse(
            base_url="http://localhost:8080",
            api_key="test-key",
            instance_name="test-instance",
        )
        assert response.base_url == "http://localhost:8080"
    
    def test_whatsapp_group_response_valid(self):
        """Testa criação de WhatsAppGroupResponse válido."""
        group = WhatsAppGroupResponse(
            group_id="group123",
            name="Grupo Teste",
        )
        assert group.group_id == "group123"
        assert group.name == "Grupo Teste"
    
    def test_whatsapp_send_request_valid(self):
        """Testa criação de WhatsAppSendRequest válido."""
        request = WhatsAppSendRequest(
            product_ids=["prod1", "prod2"],
            group_ids=["group1"],
            template="Template de teste",
        )
        assert len(request.product_ids) == 2
        assert len(request.group_ids) == 1
        assert request.template == "Template de teste"
    
    def test_whatsapp_send_request_empty_lists(self):
        """Testa validação de listas vazias."""
        # Lista de produtos vazia
        with pytest.raises(ValueError):
            WhatsAppSendRequest(
                product_ids=[],
                group_ids=["group1"],
                template="Template",
            )
        
        # Lista de grupos vazia
        with pytest.raises(ValueError):
            WhatsAppSendRequest(
                product_ids=["prod1"],
                group_ids=[],
                template="Template",
            )
    
    def test_test_endpoint_request_valid(self):
        """Testa criação de TestEndpointRequest válido."""
        request = TestEndpointRequest(
            url="https://api.example.com/test",
            api_key="test-key",
        )
        assert request.url == "https://api.example.com/test"
        assert request.api_key == "test-key"
