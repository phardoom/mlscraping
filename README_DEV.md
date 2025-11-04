# Guia de Desenvolvimento

Este documento descreve as melhorias implementadas na refatoração do projeto.

## 📋 Estrutura do Projeto

```
/workspace/
├── server.py              # Servidor principal (64 linhas)
├── api/                   # Módulos da API
│   ├── __init__.py
│   ├── schemas.py         # Schemas Pydantic para validação
│   ├── scrape.py          # Endpoints de scraping
│   ├── whatsapp.py        # Endpoints WhatsApp
│   └── products.py        # Endpoints de produtos
├── static/                # Arquivos estáticos
│   ├── css/
│   │   └── main.css
│   └── js/
│       └── main.js
├── templates/             # Templates HTML
│   └── index.html
├── tests/                 # Testes unitários
│   ├── __init__.py
│   ├── conftest.py
│   └── api/
│       ├── test_scrape.py
│       ├── test_products.py
│       └── test_whatsapp.py
├── run_dev.py            # Script para desenvolvimento com hot-reload
└── pytest.ini            # Configuração do pytest
```

## ✅ Melhorias Implementadas

### 1. Validação de Dados com Pydantic Schemas

Todos os endpoints agora usam schemas Pydantic para validação automática de dados:

- **Schemas criados** (`api/schemas.py`):
  - `ScrapeStartRequest` / `ScrapeStartResponse`
  - `ScrapeStopResponse`
  - `StatusResponse`
  - `WhatsAppConfigRequest` / `WhatsAppConfigResponse`
  - `WhatsAppGroupResponse`
  - `WhatsAppSendRequest` / `WhatsAppSendResponse`
  - `ProductResponse`
  - `ExportResponse`
  - `TestEndpointRequest`

**Benefícios**:
- Validação automática de tipos e valores
- Documentação automática no Swagger/OpenAPI
- Mensagens de erro mais claras
- Type safety

### 2. Testes Unitários

Testes abrangentes foram criados para cada módulo:

- **`tests/api/test_scrape.py`**: Testes para endpoints de scraping
- **`tests/api/test_products.py`**: Testes para endpoints de produtos
- **`tests/api/test_whatsapp.py`**: Testes para endpoints WhatsApp

**Como executar**:
```bash
# Executar todos os testes
pytest

# Executar testes específicos
pytest tests/api/test_scrape.py

# Executar com verbosidade
pytest -v

# Executar com cobertura
pytest --cov=api --cov-report=html
```

### 3. Hot-Reload para Desenvolvimento

Sistema de hot-reload implementado para desenvolvimento:

**Opção 1: Usar script dedicado**:
```bash
python run_dev.py
```

**Opção 2: Usar variável de ambiente**:
```bash
DEV_MODE=true python server.py
```

**Monitora automaticamente**:
- Arquivos Python em `./api`
- Arquivos HTML em `./templates`
- Arquivos CSS e JS em `./static`

## 🚀 Como Usar

### Execução em Produção
```bash
python server.py
```

### Execução em Desenvolvimento (com hot-reload)
```bash
python run_dev.py
# ou
DEV_MODE=true python server.py
```

### Executar Testes
```bash
# Instalar dependências de teste
pip install -r requirements.txt

# Executar testes
pytest

# Com cobertura
pytest --cov=api
```

## 📝 Documentação da API

A documentação automática está disponível em:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

Os schemas Pydantic garantem que a documentação seja sempre atualizada e precisa.

## 🔧 Configuração

### Variáveis de Ambiente

- `DEV_MODE`: Habilita hot-reload quando definido como `true`

### Estrutura de Testes

Os testes usam:
- `pytest` como framework
- `TestClient` do FastAPI para testes de integração
- Fixtures compartilhadas em `conftest.py`

## 📊 Métricas de Refatoração

- **server.py**: Reduzido de 1073 para 64 linhas (~94% de redução)
- **Código organizado**: Endpoints separados por responsabilidade
- **Validação**: 100% dos endpoints com schemas Pydantic
- **Cobertura de testes**: Testes unitários para todos os módulos principais

## 🎯 Próximos Passos (Opcional)

1. Adicionar testes de integração
2. Implementar CI/CD com GitHub Actions
3. Adicionar métricas e monitoramento
4. Criar documentação mais detalhada da API
