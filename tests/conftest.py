"""Configurações compartilhadas para testes."""

import pytest
from fastapi.testclient import TestClient

from api import products, scrape, whatsapp
from server import app


@pytest.fixture
def client():
    """Cria um cliente de teste para a aplicação."""
    return TestClient(app)


@pytest.fixture
def scrape_router():
    """Cria router de scraping para testes."""
    return scrape.create_router()


@pytest.fixture
def products_router():
    """Cria router de produtos para testes."""
    return products.create_router()


@pytest.fixture
def whatsapp_router():
    """Cria router de WhatsApp para testes."""
    return whatsapp.create_router()
