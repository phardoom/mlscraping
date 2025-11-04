"""Testes unitários para api/products.py."""

import pytest
from fastapi.testclient import TestClient

from api import products
from api.schemas import ExportResponse, ProductResponse


class TestProductsEndpoints:
    """Testes para os endpoints de produtos."""
    
    def test_list_products_endpoint(self, client):
        """Testa endpoint de listagem de produtos."""
        response = client.get("/products")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_list_products_with_limit(self, client):
        """Testa endpoint com limite customizado."""
        response = client.get("/products?limit=10")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 10
    
    def test_export_endpoint(self, client):
        """Testa endpoint de exportação."""
        response = client.get("/export")
        assert response.status_code == 200
        data = response.json()
        assert "csv" in data
        assert "json" in data
        assert "txt" in data
    
    def test_categories_endpoint(self, client):
        """Testa endpoint de categorias."""
        response = client.get("/categories")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0


class TestProductsSchemas:
    """Testes para os schemas de produtos."""
    
    def test_product_response_valid(self):
        """Testa criação de ProductResponse válido."""
        product = ProductResponse(
            id_meli="MLB123",
            title="Produto Teste",
            url="https://mercadolivre.com.br/produto",
            price=99.90,
        )
        assert product.id_meli == "MLB123"
        assert product.title == "Produto Teste"
        assert product.price == 99.90
    
    def test_export_response_valid(self):
        """Testa criação de ExportResponse válido."""
        export = ExportResponse(
            csv="/path/to/file.csv",
            json="/path/to/file.json",
            txt="/path/to/file.txt",
        )
        assert export.csv == "/path/to/file.csv"
        assert export.json == "/path/to/file.json"
        assert export.txt == "/path/to/file.txt"
