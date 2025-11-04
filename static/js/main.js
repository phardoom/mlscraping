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

async function stop() { 
  await fetch('/scrape/stop', {method:'POST'}); 
  log('Parando...', 'err'); 
}

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

// Event listeners
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

// WebSocket
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
