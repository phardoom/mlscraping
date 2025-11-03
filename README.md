# WebScraping Mercado Livre (Mais Vendidos → Links para WhatsApp)

Projeto em Python com Playwright + Typer para:
- Logar na sua conta do Mercado Livre e reutilizar a sessão
- Coletar itens a partir de uma URL de listagem (ex.: "Mais vendidos")
- Abrir cada produto, clicar em "Compartilhar" e copiar o link (afiliado se sua conta habilitar)
- Capturar dados principais (título, preço, desconto, rating, imagem)
- Exportar CSV, JSON e um arquivo `messages.txt` pronto para copiar/colar nos grupos

## Requisitos
- Python 3.10+
- `pip install -r requirements.txt`
- Instalar navegadores do Playwright: `python -m playwright install`

## Estrutura
- `main.py` — CLI (`login`, `scrape`)
- `config.py` — Settings com Pydantic
- `models.py` — Modelos (Product, AffiliateLink, Message)
- `browser.py` — Sessão Playwright (state persistido)
- `scraper.py` — Lógica de scraping (listagem + produto)
- `messages.py` — Templates WhatsApp
- `store.py` — SQLite + exports (CSV/JSON/messages)
- `data/state/storage_state.json` — Sessão salva após login

## Uso rápido
1) Login (abre navegador para você entrar na conta):
```
python -m main login
```
2) Scraping (exemplo com 50 itens de uma URL de listagem):
```
python -m main scrape --url "https://www.mercadolivre.com.br/mais-vendidos" --max-items 50
```
Com filtros (opcionais):
```
python -m main scrape --url "<URL>" --max-items 50 --min-discount 20 --min-rating 4.0 --price-min 50 --price-max 800
```

3) Exportar novamente (CSV/JSON/messages) sem rodar scraping:
```
python -m main export
```

4) Sincronizar imagens faltantes:
```
python -m main sync-images
```

## Interface Web (Acompanhamento em tempo real)
- Inicie o servidor: `python -m server`
- Abra: `http://localhost:8000`
- Cole a URL de listagem (ex.: "https://www.mercadolivre.com.br/mais-vendidos"), defina `max_items` e clique em "Iniciar".
- A página mostra o status em tempo real (via WebSocket), lista itens e permite exportar CSV/JSON/messages.

Observação: o servidor reutiliza a sessão salva em `data/state/storage_state.json`. Faça o `python -m main login` antes do primeiro uso.
Saídas em `data/out/` e imagens em `data/images/`.

Observações:
- O botão "Compartilhar" precisa estar disponível e copiar o link para a área de transferência; o app concede permissões de `clipboard-read`/`clipboard-write`.
- Caso o modal de compartilhamento não copie o link, o app tenta ler o campo do modal; por fim, usa o link do produto com UTMs como fallback.
- Envio para WhatsApp é manual (arquivo `messages.txt`).
