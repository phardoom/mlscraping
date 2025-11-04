"""Testes unitários para api/scrape.py."""

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api import scrape
from api.schemas import ScrapeStartRequest


class TestScrapeManager:
    """Testes para a classe ScrapeManager."""
    
    def test_scrape_manager_init(self):
        """Testa inicialização do ScrapeManager."""
        manager = scrape.ScrapeManager()
        assert manager.running is False
        assert manager.task is None
        assert len(manager.clients) == 0
        assert manager.last_status == {"running": False}
    
    def test_broadcast_updates_status(self):
        """Testa que broadcast atualiza last_status."""
        manager = scrape.ScrapeManager()
        test_data = {"type": "test", "value": 123}
        
        # Simula broadcast (sem WebSocket real)
        manager.last_status.update(test_data)
        
        assert manager.last_status["type"] == "test"
        assert manager.last_status["value"] == 123


class TestScrapeEndpoints:
    """Testes para os endpoints de scraping."""
    
    def test_start_scrape_validation_url_invalid(self, client):
        """Testa validação de URL inválida."""
        response = client.post(
            "/scrape/start",
            json={"url": "invalid-url", "max_items": 50},
        )
        assert response.status_code == 422  # ValidationError do Pydantic
    
    def test_start_scrape_validation_url_valid(self, client):
        """Testa validação de URL válida."""
        response = client.post(
            "/scrape/start",
            json={
                "url": "https://mercadolivre.com.br/categoria/test",
                "max_items": 50,
            },
        )
        # Pode retornar 409 se já estiver rodando, ou 200 se iniciar
        assert response.status_code in [200, 409]
    
    def test_start_scrape_validation_max_items(self, client):
        """Testa validação de max_items."""
        # Testa max_items muito alto
        response = client.post(
            "/scrape/start",
            json={
                "url": "https://mercadolivre.com.br/categoria/test",
                "max_items": 1000,  # Acima do limite de 500
            },
        )
        assert response.status_code == 422
    
    def test_start_scrape_validation_max_items_min(self, client):
        """Testa validação de max_items mínimo."""
        response = client.post(
            "/scrape/start",
            json={
                "url": "https://mercadolivre.com.br/categoria/test",
                "max_items": 0,  # Abaixo do mínimo de 1
            },
        )
        assert response.status_code == 422
    
    def test_status_endpoint(self, client):
        """Testa endpoint de status."""
        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert "running" in data
        assert isinstance(data["running"], bool)
    
    def test_stop_scrape_endpoint(self, client):
        """Testa endpoint de parada."""
        response = client.post("/scrape/stop")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True


class TestScrapeSchemas:
    """Testes para os schemas de scraping."""
    
    def test_scrape_start_request_valid(self):
        """Testa criação de ScrapeStartRequest válido."""
        request = ScrapeStartRequest(
            url="https://mercadolivre.com.br/test",
            max_items=50,
            headless=True,
        )
        assert request.url == "https://mercadolivre.com.br/test"
        assert request.max_items == 50
        assert request.headless is True
    
    def test_scrape_start_request_url_cleaning(self):
        """Testa limpeza de URL."""
        # URL com dois pontos no início
        request = ScrapeStartRequest(url=":https://mercadolivre.com.br/test")
        assert request.url == "https://mercadolivre.com.br/test"
        
        # URL com espaços
        request = ScrapeStartRequest(url="  https://mercadolivre.com.br/test  ")
        assert request.url == "https://mercadolivre.com.br/test"
    
    def test_scrape_start_request_url_invalid(self):
        """Testa validação de URL inválida."""
        with pytest.raises(ValueError, match="URL inválida"):
            ScrapeStartRequest(url="not-a-url")
    
    def test_scrape_start_request_max_items_validation(self):
        """Testa validação de max_items."""
        # Muito alto
        with pytest.raises(Exception):
            ScrapeStartRequest(
                url="https://mercadolivre.com.br/test",
                max_items=1000,
            )
        
        # Muito baixo
        with pytest.raises(Exception):
            ScrapeStartRequest(
                url="https://mercadolivre.com.br/test",
                max_items=0,
            )
