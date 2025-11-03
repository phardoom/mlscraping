from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, Optional

import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from loguru import logger

from config import MELI_CATEGORIES, get_settings
from logging_setup import setup_logging
from models import MessageTemplate, WhatsAppConfig
from runner import run_scrape
from store import Repo
from whatsapp import EvolutionAPIClient, send_products_to_whatsapp


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia o ciclo de vida da aplicação."""
    # Startup
    setup_logging()
    settings = get_settings()
    # Garante pastas
    settings.out_dir.mkdir(parents=True, exist_ok=True)
    settings.images_dir.mkdir(parents=True, exist_ok=True)
    settings.state_path.parent.mkdir(parents=True, exist_ok=True)
    Repo(settings.db_path).init()
    yield
    # Shutdown (se necessário)


app = FastAPI(title="ML Scraper UI", version="0.1.0", lifespan=lifespan)


class ScrapeManager:
    def __init__(self) -> None:
        self.running: bool = False
        self.task: Optional[asyncio.Task[Any]] = None
        self.clients: set[WebSocket] = set()
        self.last_status: dict[str, Any] = {"running": False}

    async def broadcast(self, data: dict) -> None:
        self.last_status.update(data if isinstance(data, dict) else {})
        stale: list[WebSocket] = []
        for ws in self.clients:
            try:
                await ws.send_json(data)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.clients.discard(ws)

    async def start(self, *, url: str, max_items: int, category: Optional[str] = None, settings: Optional[Any] = None) -> None:
        if self.running:
            raise RuntimeError("Scrape já em execução")

        if settings is None:
            settings = get_settings()
        settings.max_items = max_items
        repo = Repo(settings.db_path)
        repo.init()

        async def progress(ev: dict) -> None:
            await self.broadcast(ev)

        async def runner() -> None:
            self.running = True
            try:
                await self.broadcast({"type": "status", "running": True})
                await run_scrape(settings, repo, url=url, max_items=max_items, category=category, progress=progress)
            except Exception as e:  # noqa: BLE001
                logger.exception("Erro no scraping")
                await self.broadcast({"type": "error", "message": str(e)})
            finally:
                self.running = False
                await self.broadcast({"type": "status", "running": False})

        self.task = asyncio.create_task(runner())

    async def stop(self) -> None:
        """Para o scraping em andamento."""
        if not self.running:
            return  # Já está parado
        
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                logger.info("Scraping cancelado pelo usuário")
            except Exception as e:  # noqa: BLE001
                logger.debug(f"Erro ao parar scraping: {e}")
        
        self.running = False
        await self.broadcast({"type": "status", "running": False})


manager = ScrapeManager()


@app.get("/")
async def index() -> HTMLResponse:
    return HTMLResponse(_HTML)


@app.post("/scrape/start")
async def start_scrape(payload: dict) -> dict:
    url = payload.get("url")
    max_items = int(payload.get("max_items", 50))
    headless = payload.get("headless", True)  # Por padrão headless, mas pode ser desabilitado
    category = payload.get("category")  # Categoria opcional
    
    if not url:
        raise HTTPException(400, "url é obrigatório")
    
    # Limpar URL: remover espaços e caracteres extras
    url = url.strip()
    # Remover dois pontos e espaços no início se houver
    if url.startswith(":"):
        url = url[1:].strip()
    # Garantir que começa com http
    if not url.startswith("http"):
        raise HTTPException(400, f"URL inválida: {url}")
    
    if manager.running:
        raise HTTPException(409, "Scrape em execução")
    
    # Aplicar configuração de headless
    settings = get_settings()
    settings.headless = headless
    
    await manager.start(url=url, max_items=max_items, category=category, settings=settings)
    return {"ok": True}


@app.post("/scrape/stop")
async def stop_scrape() -> dict:
    """Para o scraping em andamento."""
    try:
        await manager.stop()
        return {"ok": True}
    except Exception as e:
        logger.error(f"Erro ao parar scraping: {e}")
        raise HTTPException(500, f"Erro ao parar: {e}")


@app.get("/favicon.ico")
async def favicon() -> dict:
    """Ignora requisições de favicon."""
    return {}


@app.get("/status")
async def status() -> dict:
    return {"running": manager.running, **manager.last_status}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    manager.clients.add(ws)
    try:
        await ws.send_json({"type": "hello", "running": manager.running})
        while True:
            # Mantém conexão viva; não esperamos mensagens do cliente
            await asyncio.sleep(60)
    except WebSocketDisconnect:
        pass
    finally:
        manager.clients.discard(ws)


@app.get("/products")
async def list_products(limit: int = 50) -> list[dict]:
    settings = get_settings()
    repo = Repo(settings.db_path)
    return repo.fetch_products_with_links(limit=limit)


@app.get("/export")
async def export_now() -> dict:
    settings = get_settings()
    repo = Repo(settings.db_path)
    csv_p, json_p, txt_p = repo.export_csv_json_messages(settings.out_dir)
    return {"csv": str(csv_p), "json": str(json_p), "txt": str(txt_p)}


@app.get("/categories")
async def list_categories() -> list[str]:
    """Retorna lista de categorias do Mercado Livre."""
    return MELI_CATEGORIES


@app.post("/whatsapp/config")
async def save_whatsapp_config(payload: dict) -> dict:
    """Salva configuração da Evolution API."""
    settings = get_settings()
    config = WhatsAppConfig(
        base_url=payload.get("base_url", ""),
        api_key=payload.get("api_key", ""),
        instance_name=payload.get("instance_name", ""),
    )
    
    # Salva em arquivo JSON
    import json
    settings.whatsapp_config_path.parent.mkdir(parents=True, exist_ok=True)
    with settings.whatsapp_config_path.open("w", encoding="utf-8") as f:
        json.dump(config.model_dump(), f, indent=2)
    
    logger.info(f"Configuração WhatsApp salva: {config.instance_name}")
    return {"ok": True}


@app.get("/whatsapp/config")
async def get_whatsapp_config() -> dict:
    """Retorna configuração salva da Evolution API."""
    settings = get_settings()
    if not settings.whatsapp_config_path.exists():
        return {"base_url": "", "api_key": "", "instance_name": ""}
    
    import json
    with settings.whatsapp_config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/whatsapp/groups")
async def list_whatsapp_groups() -> list[dict]:
    """Lista grupos disponíveis na Evolution API."""
    settings = get_settings()
    if not settings.whatsapp_config_path.exists():
        raise HTTPException(400, "Configuração WhatsApp não encontrada. Configure primeiro em /whatsapp/config")
    
    import json
    import httpx
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
            error_msg += " - Verifique se o endpoint/instância está correto"
        logger.error(f"{error_msg}: {e.response.text[:200]}")
        raise HTTPException(status_code=e.response.status_code, detail=error_msg)
    except Exception as e:
        error_msg = f"Erro ao listar grupos: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@app.get("/whatsapp/debug")
async def debug_whatsapp() -> dict:
    """Endpoint de debug para inspecionar resposta da Evolution API."""
    settings = get_settings()
    if not settings.whatsapp_config_path.exists():
        raise HTTPException(400, "Configuração WhatsApp não encontrada")
    
    import json
    import httpx
    
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


@app.post("/whatsapp/test-endpoint")
async def test_endpoint(payload: dict) -> dict:
    """Testa um endpoint específico da Evolution API."""
    import httpx
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


@app.post("/whatsapp/disable-groups-ignore")
async def disable_groups_ignore() -> dict:
    """Desativa groupsIgnore na instância."""
    settings = get_settings()
    if not settings.whatsapp_config_path.exists():
        raise HTTPException(400, "Configuração WhatsApp não encontrada")
    
    import json
    import httpx
    
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


@app.post("/whatsapp/send")
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
    
    import json
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
            from models import Product
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


_HTML = """
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8"/>
  <title>Scraper ML – Acompanhamento</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 20px; background: #f5f5f5; }
    .card { background: white; border-radius: 8px; padding: 20px; margin: 15px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
    .card h3 { margin-top: 0; color: #333; }
    input, button, select, textarea { padding: 8px; font-size: 14px; border: 1px solid #ddd; border-radius: 4px; }
    button { background: #007bff; color: white; cursor: pointer; border: none; }
    button:hover { background: #0056b3; }
    button:disabled { background: #ccc; cursor: not-allowed; }
    #log { border: 1px solid #ccc; height: 320px; overflow:auto; padding: 8px; background: #fff; font-family: monospace; font-size: 12px; }
    .row { margin: 8px 0; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
    .ok { color: #0a0; }
    .err { color: #a00; }
    table { border-collapse: collapse; width: 100%; background: white; }
    table th, table td { padding: 10px; text-align: left; border: 1px solid #ddd; }
    table th { background: #f8f9fa; font-weight: bold; }
    .modal { display: none; position: fixed; z-index: 1000; left: 0; top: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); }
    .modal-content { background: white; margin: 5% auto; padding: 20px; border-radius: 8px; width: 80%; max-width: 600px; max-height: 80vh; overflow-y: auto; }
    .modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
    .close { font-size: 28px; font-weight: bold; cursor: pointer; }
    .group-list { max-height: 200px; overflow-y: auto; border: 1px solid #ddd; padding: 10px; margin: 10px 0; }
    .group-item { padding: 5px; margin: 5px 0; }
    .group-item label { cursor: pointer; }
    textarea { width: 100%; min-height: 100px; font-family: monospace; }
    .preview { background: #f8f9fa; padding: 10px; border-radius: 4px; margin: 10px 0; white-space: pre-wrap; }
  </style>
</head>
<body>
  <h2>ML Scraper – Acompanhamento</h2>
  
  <div class="card">
    <h3>⚙️ Configuração Geral</h3>
    <div class="row">
      <input id="url" size="60" placeholder="Cole a URL da listagem (ex.: Mais vendidos)" />
      <input id="max" type="number" value="50" min="1" max="500" placeholder="Max itens" />
      <select id="category" style="min-width: 200px;">
        <option value="">Selecione uma categoria</option>
      </select>
      <label><input type="checkbox" id="headless" checked> Modo headless</label>
      <button id="start">▶️ Iniciar</button>
      <button id="stop">⏹️ Parar</button>
    </div>
    <div class="row">
      Status: <span id="status">parado</span>
    </div>
  </div>

  <div class="card">
    <h3>📱 Configuração Evolution API</h3>
    <div class="row">
      <input id="evo-url" size="40" placeholder="Base URL (ex: http://localhost:8080)" />
      <input id="evo-key" size="30" placeholder="API Key" />
      <input id="evo-instance" size="20" placeholder="Instance Name" />
      <button id="save-config">💾 Salvar Config</button>
      <button id="test-config">🔍 Testar Conexão</button>
      <button id="debug-config">🐛 Debug API</button>
    </div>
    <div class="row" style="margin-top: 10px;">
      <button id="disable-groups-ignore">🔓 Desativar groupsIgnore</button>
      <small style="color: #666;">Nota: groupsIgnore pode impedir a listagem de grupos</small>
    </div>
  </div>
  <div class="card">
    <h3>📋 Log de Execução</h3>
    <div id="log"></div>
  </div>

  <div class="card">
    <h3>📦 Produtos Extraídos</h3>
    <div class="row">
      <button id="refresh">🔄 Atualizar itens</button>
      <button id="select-all">✅ Selecionar Todos</button>
      <button id="send-whatsapp">📤 Enviar para WhatsApp</button>
      <a id="export" href="#">💾 Exportar CSV/JSON/messages</a>
    </div>
    <div id="items-table" style="margin-top: 20px;"></div>
  </div>

  <!-- Modal WhatsApp -->
  <div id="whatsapp-modal" class="modal">
    <div class="modal-content">
      <div class="modal-header">
        <h3>📤 Enviar para WhatsApp</h3>
        <span class="close" id="close-modal">&times;</span>
      </div>
      <div>
        <label><strong>Grupos:</strong></label>
        <div id="groups-list" class="group-list">Carregando grupos...</div>
        <button id="load-groups">🔄 Recarregar Grupos</button>
      </div>
      <div style="margin-top: 20px;">
        <label><strong>Template da Mensagem:</strong></label>
        <small>Placeholders: {'{titulo}'}, {'{preco}'}, {'{link}'}, {'{desconto}'}</small>
        <textarea id="message-template" placeholder="🔥 *Oferta!*\n\n{'{titulo}'}\n\n💰 Preço: {'{preco}'}\n\n🔗 {'{link}'}"></textarea>
        <div>
          <strong>Preview:</strong>
          <div id="message-preview" class="preview"></div>
        </div>
      </div>
      <div class="row" style="margin-top: 20px;">
        <button id="send-messages">✅ Enviar Mensagens</button>
        <button id="cancel-send">❌ Cancelar</button>
      </div>
    </div>
  </div>
  <pre id="items" style="display:none;"></pre>

  <script>
    const log = (msg, cls='') => {
      const el = document.getElementById('log');
      const div = document.createElement('div');
      if (cls) div.className = cls;
      div.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
      el.appendChild(div); el.scrollTop = el.scrollHeight;
    };

    // Carregar categorias
    async function loadCategories() {
      const res = await fetch('/categories');
      const cats = await res.json();
      const select = document.getElementById('category');
      cats.forEach(cat => {
        const opt = document.createElement('option');
        opt.value = cat;
        opt.textContent = cat;
        select.appendChild(opt);
      });
    }
    loadCategories();

    // Carregar config WhatsApp salva
    async function loadWhatsAppConfig() {
      const res = await fetch('/whatsapp/config');
      const config = await res.json();
      document.getElementById('evo-url').value = config.base_url || '';
      document.getElementById('evo-key').value = config.api_key || '';
      document.getElementById('evo-instance').value = config.instance_name || '';
    }
    loadWhatsAppConfig();

    async function start() {
      let url = document.getElementById('url').value.trim();
      // Remover dois pontos e espaços extras no início
      if (url.startsWith(':')) {
        url = url.substring(1).trim();
      }
      // Validar URL
      if (!url || !url.startsWith('http')) {
        log('URL inválida. Por favor, cole uma URL válida começando com http:// ou https://', 'err');
        return;
      }
      const max = document.getElementById('max').value;
      const headless = document.getElementById('headless').checked;
      const category = document.getElementById('category').value;
      log(`Iniciando scraping... URL: ${url}, Max items: ${max}, Categoria: ${category || 'N/A'}, Headless: ${headless}`);
      const res = await fetch('/scrape/start', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({url, max_items: Number(max), headless, category: category || null})});
      if (!res.ok) { log('Falha ao iniciar: ' + await res.text(), 'err'); return; }
      log('Scrape iniciado', 'ok');
    }
    async function stop() { await fetch('/scrape/stop', {method:'POST'}); log('Parando...', 'err'); }
    let selectedProducts = new Set();

    async function refresh() {
      const res = await fetch('/products');
      const data = await res.json();
      document.getElementById('items').textContent = JSON.stringify(data, null, 2);
      
      // Criar tabela HTML com os produtos
      const tableDiv = document.getElementById('items-table');
      if (data.length === 0) {
        tableDiv.innerHTML = '<p>Nenhum produto encontrado.</p>';
        return;
      }
      
      let html = '<table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; font-size: 12px;">';
      html += '<thead><tr><th><input type="checkbox" id="select-all-checkbox"></th><th>Título</th><th>Preço</th><th>Desconto</th><th>Categoria</th><th>Link Compartilhado</th><th>URL Original</th></tr></thead><tbody>';
      
      data.forEach(item => {
        const linkCompartilhado = item.link_compartilhado || 'N/A';
        const linkDisplay = linkCompartilhado.length > 50 ? linkCompartilhado.substring(0, 50) + '...' : linkCompartilhado;
        const checked = selectedProducts.has(item.id_meli) ? 'checked' : '';
        html += `<tr>
          <td><input type="checkbox" class="product-checkbox" data-id="${item.id_meli}" ${checked}></td>
          <td>${item.title || 'N/A'}</td>
          <td>R$ ${item.price ? item.price.toFixed(2).replace('.', ',') : 'N/A'}</td>
          <td>${item.discount_pct ? item.discount_pct + '%' : 'N/A'}</td>
          <td>${item.category || 'N/A'}</td>
          <td><a href="${linkCompartilhado}" target="_blank" title="${linkCompartilhado}">${linkDisplay}</a></td>
          <td><a href="${item.url}" target="_blank">Ver produto</a></td>
        </tr>`;
      });
      
      html += '</tbody></table>';
      tableDiv.innerHTML = html;

      // Event listeners para checkboxes
      document.querySelectorAll('.product-checkbox').forEach(cb => {
        cb.onchange = (e) => {
          const id = e.target.dataset.id;
          if (e.target.checked) {
            selectedProducts.add(id);
          } else {
            selectedProducts.delete(id);
          }
          updateSelectAllCheckbox();
          // Debug: mostra quantos produtos estão selecionados
          console.log('Produtos selecionados:', Array.from(selectedProducts));
        };
        // Sincroniza estado inicial do checkbox com selectedProducts
        const id = cb.dataset.id;
        if (selectedProducts.has(id)) {
          cb.checked = true;
        }
      });

      document.getElementById('select-all-checkbox').onchange = (e) => {
        const checked = e.target.checked;
        document.querySelectorAll('.product-checkbox').forEach(cb => {
          cb.checked = checked;
          const id = cb.dataset.id;
          if (checked) {
            selectedProducts.add(id);
          } else {
            selectedProducts.delete(id);
          }
        });
      };

      updateSelectAllCheckbox();
    }

    function updateSelectAllCheckbox() {
      const allChecked = document.querySelectorAll('.product-checkbox').length > 0 && 
                         Array.from(document.querySelectorAll('.product-checkbox')).every(cb => cb.checked);
      document.getElementById('select-all-checkbox').checked = allChecked;
    }
    async function exportNow() {
      const res = await fetch('/export');
      const data = await res.json();
      log('Exportado: ' + data.csv);
    }

    // WhatsApp functions
    async function saveWhatsAppConfig() {
      const config = {
        base_url: document.getElementById('evo-url').value.trim(),
        api_key: document.getElementById('evo-key').value.trim(),
        instance_name: document.getElementById('evo-instance').value.trim(),
      };
      const res = await fetch('/whatsapp/config', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(config)
      });
      if (res.ok) {
        log('✅ Configuração WhatsApp salva', 'ok');
      } else {
        log('❌ Erro ao salvar configuração: ' + await res.text(), 'err');
      }
    }

    async function testConnection() {
      log('🔍 Testando conexão com Evolution API...');
      try {
        // Tenta salvar a config temporariamente
        const config = {
          base_url: document.getElementById('evo-url').value.trim(),
          api_key: document.getElementById('evo-key').value.trim(),
          instance_name: document.getElementById('evo-instance').value.trim(),
        };
        
        // Valida campos vazios
        if (!config.base_url || !config.api_key || !config.instance_name) {
          log('❌ Preencha todos os campos da configuração', 'err');
          return;
        }
        
        const saveRes = await fetch('/whatsapp/config', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(config)
        });
        
        if (!saveRes.ok) {
          log('❌ Erro ao salvar configuração: ' + await saveRes.text(), 'err');
          return;
        }
        
        // Tenta listar grupos
        const res = await fetch('/whatsapp/groups');
        if (!res.ok) {
          let errorMsg = '';
          try {
            const errorData = await res.json();
            errorMsg = errorData.detail || errorData.message || JSON.stringify(errorData);
          } catch {
            errorMsg = await res.text();
          }
          log('❌ Erro ao testar conexão: ' + errorMsg, 'err');
          if (res.status === 401) {
            log('💡 Dica: Verifique se a API Key está correta (deve ser a AUTHENTICATION_API_KEY do Portainer)', 'err');
          } else if (res.status === 404) {
            log('💡 Dica: Verifique se o endpoint/instância está correto', 'err');
          }
          return;
        }
        const groups = await res.json();
        if (groups.length === 0) {
          log('⚠️ Conexão OK, mas nenhum grupo encontrado na instância.', 'err');
          log('💡 Dica: Verifique se a instância está conectada e se há grupos disponíveis', 'err');
          return;
        }
        log(`✅ Conexão OK! Encontrados ${groups.length} grupos.`, 'ok');
        
        // Mostra lista de grupos na tela
        const tableDiv = document.getElementById('items-table');
        const oldContent = tableDiv.innerHTML;
        let html = '<h4>Grupos encontrados na instância:</h4><table border="1" cellpadding="8" style="border-collapse: collapse; width: 100%; font-size: 12px; margin-bottom: 20px;">';
        html += '<thead><tr><th>ID do Grupo</th><th>Nome</th></tr></thead><tbody>';
        groups.forEach(g => {
          html += `<tr><td>${g.group_id}</td><td>${g.name}</td></tr>`;
        });
        html += '</tbody></table>';
        tableDiv.innerHTML = html + oldContent;
      } catch (e) {
        log('❌ Erro ao testar conexão: ' + e.message, 'err');
      }
    }

    async function loadGroups() {
      const groupsDiv = document.getElementById('groups-list');
      groupsDiv.innerHTML = '<p>Carregando grupos...</p>';
      try {
        const res = await fetch('/whatsapp/groups');
        if (!res.ok) {
          const errorText = await res.text();
          groupsDiv.innerHTML = '<p style="color: red;">Erro: ' + errorText + '</p>';
          return;
        }
        const groups = await res.json();
        if (groups.length === 0) {
          groupsDiv.innerHTML = '<p style="color: orange;">⚠️ Nenhum grupo encontrado na instância. Verifique se a instância está conectada e há grupos disponíveis.</p>';
          return;
        }
        let html = '';
        html += `<p><strong>Selecione um ou mais grupos para enviar:</strong></p>`;
        html += `<div style="margin: 10px 0;"><label><input type="checkbox" id="select-all-groups" onchange="toggleAllGroups(this.checked)"> Selecionar todos</label></div>`;
        groups.forEach(g => {
          html += `<div class="group-item"><label><input type="checkbox" class="group-checkbox" data-id="${g.group_id}" data-name="${g.name}"> <strong>${g.name}</strong><br><small style="color: #666;">${g.group_id}</small></label></div>`;
        });
        groupsDiv.innerHTML = html;
        
        // Log de grupos carregados
        log(`✅ ${groups.length} grupo(s) carregado(s)`, 'ok');
      } catch (e) {
        groupsDiv.innerHTML = '<p style="color: red;">Erro ao carregar grupos: ' + e.message + '</p>';
        log('❌ Erro ao carregar grupos: ' + e.message, 'err');
      }
    }
    
    function toggleAllGroups(checked) {
      document.querySelectorAll('.group-checkbox').forEach(cb => {
        cb.checked = checked;
      });
    }

    function updatePreview() {
      const template = document.getElementById('message-template').value;
      // Remove aspas extras e processa placeholders corretamente
      let preview = template
        .replace(/'\{'/g, '{')  // Remove '{'
        .replace(/'}'/g, '}')   // Remove '}'
        .replace(/{titulo}/g, 'Exemplo: Produto Teste')
        .replace(/{preco}/g, 'R$ 99,90')
        .replace(/{link}/g, 'https://mercadolivre.com/sec/ABC123')
        .replace(/{desconto}/g, '20% OFF');
      document.getElementById('message-preview').textContent = preview;
    }

    function openWhatsAppModal() {
      // Recarrega selectedProducts do estado atual dos checkboxes
      selectedProducts.clear();
      document.querySelectorAll('.product-checkbox:checked').forEach(cb => {
        selectedProducts.add(cb.dataset.id);
      });
      
      if (selectedProducts.size === 0) {
        log('⚠️ Selecione pelo menos um produto antes de enviar', 'err');
        return;
      }
      
      log(`📤 Preparando envio de ${selectedProducts.size} produto(s) selecionado(s)...`, 'ok');
      document.getElementById('whatsapp-modal').style.display = 'block';
      loadGroups();
      updatePreview();
    }

    function closeWhatsAppModal() {
      document.getElementById('whatsapp-modal').style.display = 'none';
    }

    async function sendWhatsAppMessages() {
      log('🔵 [DEBUG] sendWhatsAppMessages chamado', 'ok');
      
      // Garante que selectedProducts está atualizado
      selectedProducts.clear();
      document.querySelectorAll('.product-checkbox:checked').forEach(cb => {
        selectedProducts.add(cb.dataset.id);
      });
      
      log(`🔵 [DEBUG] Produtos selecionados: ${selectedProducts.size}`, 'ok');
      console.log('Produtos selecionados:', Array.from(selectedProducts));
      
      const selectedGroups = Array.from(document.querySelectorAll('.group-checkbox:checked')).map(cb => ({
        id: cb.dataset.id,
        name: cb.dataset.name
      }));
      
      log(`🔵 [DEBUG] Grupos selecionados: ${selectedGroups.length}`, 'ok');
      console.log('Grupos selecionados:', selectedGroups);
      
      if (selectedProducts.size === 0) {
        log('⚠️ Selecione pelo menos um produto antes de enviar', 'err');
        return;
      }
      
      if (selectedGroups.length === 0) {
        log('⚠️ Selecione pelo menos um grupo', 'err');
        return;
      }
      
      const template = document.getElementById('message-template').value;
      log(`🔵 [DEBUG] Template length: ${template.length}`, 'ok');
      
      if (!template.trim()) {
        log('⚠️ Template de mensagem não pode estar vazio', 'err');
        return;
      }

      // Remove aspas extras do template se houver
      let cleanedTemplate = template.replace(/'\{'/g, '{').replace(/'}'/g, '}');

      const payload = {
        product_ids: Array.from(selectedProducts),
        group_ids: selectedGroups.map(g => g.id),
        template: cleanedTemplate
      };

      log(`📤 Enviando ${selectedProducts.size} produto(s) para ${selectedGroups.length} grupo(s)...`, 'ok');
      selectedGroups.forEach(g => {
        log(`   - ${g.name}`, 'ok');
      });
      
      log('🔵 [DEBUG] Fazendo fetch para /whatsapp/send...', 'ok');
      
      try {
        const res = await fetch('/whatsapp/send', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload)
        });

        log(`🔵 [DEBUG] Resposta recebida: status ${res.status}`, 'ok');

        if (res.ok) {
          const data = await res.json();
          log('✅ ' + data.message, 'ok');
          log(`🔵 [DEBUG] Resposta completa: ${JSON.stringify(data)}`, 'ok');
          closeWhatsAppModal();
        } else {
          const errorText = await res.text();
          log('❌ Erro ao enviar: ' + errorText, 'err');
          log(`❌ Status HTTP: ${res.status}`, 'err');
        }
      } catch (e) {
        log('❌ Exceção ao enviar: ' + e.message, 'err');
        console.error('Erro completo:', e);
      }
    }

    async function debugAPI() {
      log('🐛 Obtendo resposta raw da API...');
      try {
        const res = await fetch('/whatsapp/debug');
        const data = await res.json();
        log('=== RESPONSE DEBUG ===', 'ok');
        log('Status Code: ' + data.status_code);
        log('URL: ' + data.url);
        log('API Key (prefixo): ' + (data.api_key_prefix || 'N/A'));
        if (data.note) {
          log('Nota: ' + data.note, 'err');
        }
        log('Raw Response: ' + data.raw_response);
        if (data.error) {
          log('Erro: ' + data.error, 'err');
        }
        log('=== TESTANDO ENDPOINTS ALTERNATIVOS ===', 'ok');
        // Testa endpoint de verificação de instância primeiro
        const config = {
          base_url: document.getElementById('evo-url').value.trim(),
          api_key: document.getElementById('evo-key').value.trim(),
          instance_name: document.getElementById('evo-instance').value.trim(),
        };
        if (config.base_url && config.api_key && config.instance_name) {
          const baseUrlClean = config.base_url.replace(/\/$/, '');
          const testEndpoints = [
            // Endpoints de verificação de instância
            {url: `${baseUrlClean}/instance/fetchInstances`, name: 'Verificar instâncias'},
            {url: `${baseUrlClean}/instance/connectionState/${config.instance_name}`, name: 'Estado da conexão'},
            {url: `${baseUrlClean}/${config.instance_name}/profile`, name: 'Perfil da instância'},
            // Endpoints de grupos
            {url: `${baseUrlClean}/group/fetchAllGroups/${config.instance_name}?getParticipants=true`, name: 'Grupos (fetchAllGroups com participantes)'},
            {url: `${baseUrlClean}/group/fetchAllGroups/${config.instance_name}?getParticipants=false`, name: 'Grupos (fetchAllGroups sem participantes)'},
            {url: `${baseUrlClean}/group/allGroups/${config.instance_name}`, name: 'Grupos (allGroups)'},
            {url: `${baseUrlClean}/${config.instance_name}/group`, name: 'Grupos (instance/group)'},
            {url: `${baseUrlClean}/chat/fetchAllGroups/${config.instance_name}`, name: 'Chat (fetchAllGroups)'},
            {url: `${baseUrlClean}/chat/fetchGroups/${config.instance_name}`, name: 'Chat (fetchGroups)'},
          ];
          for (const ep of testEndpoints) {
            try {
              const testRes = await fetch('/whatsapp/test-endpoint', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({url: ep.url, api_key: config.api_key})
              });
              const testData = await testRes.json();
              const status = testData.status_code;
              if (status === 200) {
                log(`✅ ${status} - ${ep.name}: ${ep.url}`, 'ok');
                if (testData.response) {
                  log(`   Resposta: ${testData.response.substring(0, 200)}`, 'ok');
                }
              } else if (status === 401) {
                log(`🔐 ${status} - ${ep.name}: Autenticação falhou`, 'err');
              } else if (status === 404) {
                log(`❌ ${status} - ${ep.name}: Não encontrado`, 'err');
              } else {
                log(`⚠️ ${status} - ${ep.name}: ${ep.url}`, 'err');
              }
            } catch (e) {
              log(`❌ Erro ao testar ${ep.name}: ${e.message}`, 'err');
            }
          }
        }
        log('=== FIM DEBUG ===', 'ok');
      } catch (e) {
        log('❌ Erro ao fazer debug: ' + e.message, 'err');
      }
    }

    async function disableGroupsIgnore() {
      log('🔓 Desativando groupsIgnore na instância...');
      try {
        const res = await fetch('/whatsapp/disable-groups-ignore', {method: 'POST'});
        const data = await res.json();
        log('Status Code: ' + data.status_code);
        log('Response: ' + JSON.stringify(data.response));
        if (data.status_code === 200) {
          log('✅ groupsIgnore desativado com sucesso!', 'ok');
          log('Aguarde alguns segundos e teste a conexão novamente.', 'ok');
        }
      } catch (e) {
        log('❌ Erro: ' + e.message, 'err');
      }
    }

    document.getElementById('start').onclick = start;
    document.getElementById('stop').onclick = stop;
    document.getElementById('refresh').onclick = refresh;
    document.getElementById('export').onclick = (e)=>{e.preventDefault(); exportNow();};
    document.getElementById('save-config').onclick = saveWhatsAppConfig;
    document.getElementById('test-config').onclick = testConnection;
    document.getElementById('debug-config').onclick = debugAPI;
    document.getElementById('disable-groups-ignore').onclick = disableGroupsIgnore;
    document.getElementById('load-groups').onclick = loadGroups;
    document.getElementById('send-whatsapp').onclick = openWhatsAppModal;
    document.getElementById('close-modal').onclick = closeWhatsAppModal;
    document.getElementById('cancel-send').onclick = closeWhatsAppModal;
    document.getElementById('send-messages').onclick = sendWhatsAppMessages;
    document.getElementById('select-all').onclick = () => {
      document.getElementById('select-all-checkbox').click();
    };
    document.getElementById('message-template').oninput = updatePreview;
    
    // Fechar modal ao clicar fora
    window.onclick = (e) => {
      const modal = document.getElementById('whatsapp-modal');
      if (e.target === modal) {
        closeWhatsAppModal();
      }
    };
    
    // Carrega produtos ao iniciar
    refresh();

    const ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
    ws.onmessage = (ev) => {
      const data = JSON.parse(ev.data);
      if (data.type==='status') {
        document.getElementById('status').textContent = data.running ? 'rodando' : 'parado';
      } else if (data.type==='item_begin') {
        log(`Item ${data.index}/${data.total}: ` + data.url);
      } else if (data.type==='item_saved') {
        const shareInfo = data.share ? ` [Link: ${data.share.substring(0, 40)}...]` : '';
        log('Salvo: ' + data.title + shareInfo, 'ok');
      } else if (data.type==='error') {
        log('Erro: ' + data.message, 'err');
      } else if (data.type==='list_collected') {
        log(`URLs coletadas: ${data.count}`, data.count > 0 ? 'ok' : 'err');
        if (data.count === 0) {
          log('Nenhum produto encontrado. Verifique a URL e tente novamente.', 'err');
        }
      } else if (data.type==='status_message') {
        log(data.message);
      } else if (data.type==='end') {
        log('Concluído', 'ok');
        refresh(); // Atualiza a tabela automaticamente ao finalizar
      }
    };
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)

