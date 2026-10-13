const state = {
  status: "Rascunho",
  items: [],
  clients: [],
  products: [],
  history: [],
  serverHistory: [],
  localHistory: [],
  currentQuoteId: null,
  currentLocalId: null,
  generatedPdf: null
};

const LOCAL_HISTORY_KEY = "wvl_history_v1";

const $ = (id) => document.getElementById(id);

function moneyValue(value) {
  let text = String(value || "0").trim();
  text = text.includes(",") ? text.replace(/\./g, "").replace(",", ".") : text;
  const parsed = Number.parseFloat(text);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatBRL(value) {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
}

function toast(message) {
  const box = $("toast");
  box.textContent = message;
  box.hidden = false;
  clearTimeout(box.timer);
  box.timer = setTimeout(() => { box.hidden = true; }, 3600);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function quoteTotal(data = payload()) {
  const subtotal = (data.items || []).reduce((sum, item) => (
    sum + Math.max(0, moneyValue(item.quantity) * moneyValue(item.unit_price) - moneyValue(item.discount))
  ), 0);
  return subtotal + subtotal * moneyValue(data.tax_rate) / 100;
}

function invalidateGeneratedPdf() {
  state.generatedPdf = null;
  $("pdfStatus").textContent = "O PDF será gerado automaticamente ao tocar em Enviar PDF.";
  $("downloadLink").href = "#";
  $("downloadLink").classList.add("disabled");
}

function payload() {
  return {
    quote_id: state.currentQuoteId,
    client_name: $("clientName").value.trim(),
    phone: $("phone").value.trim(),
    vehicle: $("vehicle").value.trim(),
    plate: $("plate").value.trim(),
    status: state.status,
    tax_rate: $("taxRate").value,
    notes: $("notes").value,
    include_cover: $("includeCover").checked,
    items: state.items
  };
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Falha no servidor");
  return data;
}

function loadLocalHistory() {
  try {
    const saved = JSON.parse(localStorage.getItem(LOCAL_HISTORY_KEY) || "[]");
    return Array.isArray(saved) ? saved : [];
  } catch {
    return [];
  }
}

function persistLocalHistory() {
  try {
    localStorage.setItem(LOCAL_HISTORY_KEY, JSON.stringify(state.localHistory.slice(0, 200)));
    return true;
  } catch {
    return false;
  }
}

function meaningfulQuote(data = payload()) {
  return Boolean(data.client_name || (data.items || []).some((item) => item.description.trim()));
}

function newLocalId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function saveLocalDraft() {
  const data = payload();
  if (!meaningfulQuote(data)) return null;
  state.currentLocalId ||= newLocalId();
  const record = {
    id: state.currentLocalId,
    server_id: state.currentQuoteId,
    updated_at: new Date().toISOString(),
    name: data.client_name || "Orçamento sem cliente",
    phone: data.phone,
    vehicle: data.vehicle,
    plate: data.plate,
    status: data.status,
    total: quoteTotal(data),
    data: JSON.parse(JSON.stringify(data))
  };
  const existing = state.localHistory.findIndex((row) => row.id === record.id);
  if (existing >= 0) state.localHistory.splice(existing, 1);
  state.localHistory.unshift(record);
  persistLocalHistory();
  mergeHistory();
  return record;
}

function mergeHistory() {
  const serverIds = new Set(state.localHistory.map((row) => Number(row.server_id)).filter(Boolean));
  const localRows = state.localHistory.map((row) => ({
    ...row,
    id: `local:${row.id}`,
    local_id: row.id,
    local: true
  }));
  const serverRows = state.serverHistory.filter((row) => !serverIds.has(Number(row.id)));
  state.history = [...localRows, ...serverRows].sort((a, b) => {
    const aDate = a.updated_at || a.created_at || "";
    const bDate = b.updated_at || b.created_at || "";
    return bDate.localeCompare(aDate);
  });
  renderHistory();
}

let autosaveTimer;
let autosaveInFlight = false;
let autosaveQueued = false;
function scheduleAutosave() {
  clearTimeout(autosaveTimer);
  if (!meaningfulQuote()) {
    $("saveStatus").textContent = "Novo orçamento";
    return;
  }
  $("saveStatus").textContent = "Salvando...";
  if (autosaveInFlight) {
    autosaveQueued = true;
    return;
  }
  autosaveTimer = setTimeout(autosave, 700);
}

async function autosave() {
  const localRecord = saveLocalDraft();
  if (!localRecord) return;
  $("saveStatus").textContent = "Salvo neste iPhone";
  const data = payload();
  if (!data.client_name || !data.items.some((item) => item.description.trim())) return;
  autosaveInFlight = true;
  try {
    const result = await api("/api/autosave", { method: "POST", body: JSON.stringify(data) });
    if (result.status === "ok") {
      localRecord.server_id = result.quote_id;
      localRecord.data.quote_id = result.quote_id;
      if (state.currentLocalId === localRecord.id) state.currentQuoteId = result.quote_id;
      state.serverHistory = result.history || state.serverHistory;
      updateMetrics(result.metrics);
      persistLocalHistory();
      mergeHistory();
      $("saveStatus").textContent = "Salvo automaticamente";
    }
  } catch {
    $("saveStatus").textContent = "Salvo neste iPhone";
  } finally {
    autosaveInFlight = false;
    if (autosaveQueued) {
      autosaveQueued = false;
      scheduleAutosave();
    }
  }
}

function setStatus(status) {
  if (state.status !== status) invalidateGeneratedPdf();
  state.status = status;
  document.querySelectorAll(".status-pill").forEach((button) => {
    button.classList.toggle("active", button.dataset.status === status);
  });
  preview();
  scheduleAutosave();
}

function fillDatalists() {
  $("clientOptions").innerHTML = state.clients.map((client) => `<option value="${client.name}"></option>`).join("");
  $("productOptions").innerHTML = state.products.map((product) => `<option value="${product.description}"></option>`).join("");
}

function fillClientByName() {
  const found = state.clients.find((client) => client.name === $("clientName").value.trim());
  if (!found) return;
  $("phone").value = found.phone || "";
  $("vehicle").value = found.vehicle || "";
  $("plate").value = found.plate || "";
  scheduleAutosave();
}

function fillProductByName() {
  const found = state.products.find((product) => product.description === $("productSearch").value.trim());
  if (!found) return;
  $("productPrice").value = found.unit_price || "";
  $("productCost").value = found.unit_cost || "";
}

function addItem(kind) {
  const isService = kind === "service";
  const descEl = isService ? $("serviceDesc") : $("productSearch");
  const priceEl = isService ? $("servicePrice") : $("productPrice");
  const costEl = isService ? $("serviceCost") : $("productCost");
  const raw = descEl.value.trim();
  if (!raw) {
    toast(isService ? "Informe o servico." : "Informe o produto.");
    return;
  }
  const prefix = isService ? "Servico - " : "Produto - ";
  const description = raw.startsWith("Servico - ") || raw.startsWith("Produto - ") ? raw : `${prefix}${raw}`;
  state.items.push({
    description,
    quantity: "1",
    unit_price: priceEl.value || "0",
    unit_cost: costEl.value || "0",
    discount: "0"
  });
  invalidateGeneratedPdf();
  descEl.value = "";
  priceEl.value = "";
  costEl.value = "";
  renderItems();
  preview();
  scheduleAutosave();
}

function addEmptyItem() {
  state.items.push({ description: "", quantity: "1", unit_price: "0", unit_cost: "0", discount: "0" });
  invalidateGeneratedPdf();
  renderItems();
  scheduleAutosave();
}

function renderItems() {
  const body = $("itemsBody");
  body.innerHTML = "";
  state.items.forEach((item, index) => {
    const subtotal = Math.max(0, moneyValue(item.quantity) * moneyValue(item.unit_price) - moneyValue(item.discount));
    const row = document.createElement("tr");
    row.innerHTML = `
      <td data-label="Descrição"><input aria-label="Descrição" data-field="description" data-index="${index}" value="${item.description.replaceAll('"', "&quot;")}"></td>
      <td data-label="Quantidade"><input aria-label="Quantidade" data-field="quantity" data-index="${index}" inputmode="decimal" value="${item.quantity}"></td>
      <td data-label="Preço"><input aria-label="Preço" data-field="unit_price" data-index="${index}" inputmode="decimal" value="${item.unit_price}"></td>
      <td data-label="Custo"><input aria-label="Custo" data-field="unit_cost" data-index="${index}" inputmode="decimal" value="${item.unit_cost}"></td>
      <td data-label="Desconto"><input aria-label="Desconto" data-field="discount" data-index="${index}" inputmode="decimal" value="${item.discount}"></td>
      <td data-label="Total"><strong>${formatBRL(subtotal)}</strong></td>
      <td class="remove-cell"><button type="button" class="remove" data-remove="${index}" aria-label="Remover item ${index + 1}">Remover</button></td>
    `;
    body.appendChild(row);
  });
  if (!state.items.length) {
    body.innerHTML = `<tr class="empty-row"><td colspan="7">Nenhum item adicionado ainda.</td></tr>`;
  }
  const count = state.items.length;
  $("itemsCount").textContent = `${count} ${count === 1 ? "item" : "itens"}`;
}

function updateMetrics(metrics) {
  if (!metrics) return;
  $("metrics").innerHTML = `
    <div><span>Aprovado</span><strong>${metrics.revenue}</strong></div>
    <div><span>Conversao</span><strong>${metrics.conversion}</strong></div>
    <div><span>Em aberto</span><strong>${metrics.open_value}</strong></div>
    <div><span>Orcamentos</span><strong>${metrics.quote_count}</strong></div>
  `;
}

let previewTimer;
function preview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(async () => {
    try {
      const data = await api("/api/preview", { method: "POST", body: JSON.stringify(payload()) });
      $("quoteTotal").textContent = data.total;
      $("quoteMargin").textContent = `Margem: ${data.margin_percent} | Lucro: ${data.profit}`;
    } catch {
      $("quoteMargin").textContent = "Revise os valores do orcamento";
    }
  }, 180);
}

async function generatePdf() {
  try {
    const data = await api("/api/quotes", { method: "POST", body: JSON.stringify(payload()) });
    state.currentQuoteId = data.quote_id;
    $("pdfStatus").textContent = `PDF gerado: ${data.filename}`;
    $("downloadLink").href = data.download_url;
    $("downloadLink").setAttribute("download", data.filename);
    $("downloadLink").classList.remove("disabled");
    state.generatedPdf = {
      url: data.download_url,
      filename: data.filename,
      file: null
    };
    try {
      state.generatedPdf.file = await fetchPdfFile(data.download_url, data.filename);
    } catch {
      // O envio tentara buscar o arquivo novamente quando o usuario clicar.
    }
    state.serverHistory = data.history || state.serverHistory;
    const localRecord = saveLocalDraft();
    if (localRecord) {
      localRecord.server_id = data.quote_id;
      localRecord.data.quote_id = data.quote_id;
      persistLocalHistory();
    }
    mergeHistory();
    $("saveStatus").textContent = "Salvo e PDF gerado";
    updateMetrics(data.metrics);
    toast("PDF gerado e salvo no histórico.");
    return state.generatedPdf;
  } catch (error) {
    toast(error.message);
    return null;
  }
}

async function fetchPdfFile(url, filename) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error("Nao foi possivel preparar o PDF.");
  const blob = await response.blob();
  return new File([blob], filename, { type: "application/pdf" });
}

async function sharePdf(event) {
  event.preventDefault();
  const trigger = event.target.closest("button, a");
  if (!trigger || trigger.dataset.busy === "true") return;

  trigger.dataset.busy = "true";
  trigger.classList.add("disabled");
  const originalText = trigger.textContent;

  try {
    let generated = state.generatedPdf;
    if (!generated) {
      trigger.textContent = "Gerando PDF...";
      toast("Gerando PDF para envio...");
      generated = await generatePdf();
      if (!generated) return;
    }

    trigger.textContent = "Preparando envio...";
    toast("Preparando PDF para envio...");
    const file = generated.file || await fetchPdfFile(generated.url, generated.filename);
    generated.file = file;

    if (!navigator.share || !navigator.canShare || !navigator.canShare({ files: [file] })) {
      throw new Error("Este navegador nao permite enviar o PDF diretamente. Use o botao Download e anexe o arquivo no WhatsApp.");
    }

    await navigator.share({
      files: [file],
      title: generated.filename,
      text: "Orcamento WVL"
    });
  } catch (error) {
    if (error && error.name === "AbortError") return;
    if (error && error.name === "NotAllowedError" && state.generatedPdf) {
      toast("PDF pronto. Toque novamente em Enviar PDF para compartilhar.");
      return;
    }
    toast(error.message || "Nao foi possivel enviar o PDF.");
  } finally {
    trigger.dataset.busy = "false";
    trigger.classList.remove("disabled");
    trigger.textContent = originalText;
  }
}

async function downloadPdf(event) {
  event.preventDefault();
  const link = $("downloadLink");
  if (!link.href || link.classList.contains("disabled")) return;

  const filename = link.getAttribute("download") || "orcamento-wvl.pdf";
  try {
    toast("Preparando PDF...");
    const response = await fetch(link.href, { cache: "no-store" });
    if (!response.ok) throw new Error("Nao foi possivel baixar o PDF.");
    const blob = await response.blob();
    const file = new File([blob], filename, { type: "application/pdf" });

    if (navigator.canShare && navigator.canShare({ files: [file] })) {
      await navigator.share({
        files: [file],
        title: filename,
        text: "Orcamento WVL"
      });
      return;
    }

    const objectUrl = URL.createObjectURL(blob);
    const tempLink = document.createElement("a");
    tempLink.href = objectUrl;
    tempLink.download = filename;
    tempLink.target = "_blank";
    document.body.appendChild(tempLink);
    tempLink.click();
    tempLink.remove();
    setTimeout(() => URL.revokeObjectURL(objectUrl), 30000);
  } catch (error) {
    toast(error.message || "Abra o PDF pelo navegador para salvar.");
    window.open(link.href, "_blank", "noopener");
  }
}

function renderHistory() {
  const list = $("historyList");
  if (!state.history.length) {
    list.innerHTML = `<p class="muted">Nenhum orcamento salvo ainda.</p>`;
    return;
  }
  list.innerHTML = state.history.map((row) => `
    <div class="history-row">
      <strong>${row.local ? "Auto" : `#${row.id}`}</strong>
      <span>${escapeHtml(row.name)}<br><small>${escapeHtml(row.vehicle || "-")} ${escapeHtml(row.plate || "")}</small></span>
      <span>${escapeHtml(row.status)}</span>
      <span>R$ ${Number(row.total || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}</span>
      <button type="button" class="ghost" ${row.local ? `data-load-local="${row.local_id}"` : `data-load="${row.id}"`}>Abrir</button>
    </div>
  `).join("");
}

function applyQuoteData(data) {
  $("clientName").value = data.client_name || "";
  $("phone").value = data.phone || "";
  $("vehicle").value = data.vehicle || "";
  $("plate").value = data.plate || "";
  $("taxRate").value = data.tax_rate || "0";
  $("notes").value = data.notes || $("notes").value;
  state.status = data.status || "Rascunho";
  document.querySelectorAll(".status-pill").forEach((button) => {
    button.classList.toggle("active", button.dataset.status === state.status);
  });
  state.items = (data.items || []).map((item) => ({
    description: item.description,
    quantity: item.quantity,
    unit_price: item.unit_price,
    unit_cost: item.unit_cost,
    discount: item.discount
  }));
  invalidateGeneratedPdf();
  renderItems();
  preview();
  $("historyPanel").hidden = true;
}

async function openHistoryQuote(id) {
  try {
    const data = await api(`/api/history/${id}`);
    state.currentQuoteId = Number(id);
    state.currentLocalId = null;
    applyQuoteData(data);
    saveLocalDraft();
    $("saveStatus").textContent = "Orçamento recuperado";
  } catch (error) {
    toast(error.message);
  }
}

function openLocalHistoryQuote(id) {
  const record = state.localHistory.find((row) => row.id === id);
  if (!record) {
    toast("Orçamento não encontrado neste aparelho.");
    return;
  }
  state.currentLocalId = record.id;
  state.currentQuoteId = record.server_id || null;
  applyQuoteData(record.data);
  $("saveStatus").textContent = "Orçamento recuperado";
}

async function showHistory() {
  $("historyPanel").hidden = false;
  try {
    state.serverHistory = await api("/api/history");
  } catch {
    // O histórico salvo no aparelho continua disponível sem o servidor.
  }
  mergeHistory();
}

function resetForm() {
  clearTimeout(autosaveTimer);
  autosaveQueued = false;
  state.currentQuoteId = null;
  state.currentLocalId = null;
  $("clientName").value = "";
  $("phone").value = "";
  $("vehicle").value = "";
  $("plate").value = "";
  $("taxRate").value = "0";
  $("notes").value = "Validade da proposta: 7 dias. Pagamento conforme combinado. Pecas sujeitas a disponibilidade.";
  $("includeCover").checked = true;
  invalidateGeneratedPdf();
  state.items = [];
  setStatus("Rascunho");
  renderItems();
  preview();
  $("saveStatus").textContent = "Novo orçamento";
}

async function backup() {
  try {
    const data = await api("/api/backup", { method: "POST", body: "{}" });
    toast(`Backup criado: ${data.path}`);
  } catch (error) {
    toast(error.message);
  }
}

async function loadBootstrap() {
  const data = await api("/api/bootstrap");
  state.clients = data.clients || [];
  state.products = data.products || [];
  state.serverHistory = data.history || [];
  state.localHistory = loadLocalHistory();
  fillDatalists();
  updateMetrics(data.metrics);
  mergeHistory();
}

document.addEventListener("input", (event) => {
  const target = event.target;
  const quoteFields = ["clientName", "phone", "vehicle", "plate", "taxRate", "notes", "includeCover"];
  if ((target.dataset && target.dataset.field) || quoteFields.includes(target.id)) {
    invalidateGeneratedPdf();
  }
  if (target.dataset && target.dataset.field) {
    const item = state.items[Number(target.dataset.index)];
    item[target.dataset.field] = target.value;
    const subtotal = Math.max(0, moneyValue(item.quantity) * moneyValue(item.unit_price) - moneyValue(item.discount));
    const totalCell = target.closest("tr").querySelector("td:nth-child(6) strong");
    if (totalCell) totalCell.textContent = formatBRL(subtotal);
  }
  preview();
  scheduleAutosave();
});

document.addEventListener("click", (event) => {
  const target = event.target.closest("button, a");
  if (!target) return;
  if (target.id === "downloadLink") downloadPdf(event);
  if (target.id === "whatsappLink") sharePdf(event);
  if (target.dataset.status) setStatus(target.dataset.status);
  if (target.dataset.remove) {
    state.items.splice(Number(target.dataset.remove), 1);
    invalidateGeneratedPdf();
    renderItems();
    preview();
    scheduleAutosave();
  }
  if (target.dataset.load) openHistoryQuote(target.dataset.load);
  if (target.dataset.loadLocal) openLocalHistoryQuote(target.dataset.loadLocal);
  const action = target.dataset.action;
  if (action === "new") resetForm();
  if (action === "history") showHistory();
  if (action === "close-history") $("historyPanel").hidden = true;
  if (action === "report") window.location.href = "/relatorio-mensal";
  if (action === "send") sharePdf(event);
  if (action === "add-service") addItem("service");
  if (action === "add-product") addItem("product");
  if (action === "add-empty") addEmptyItem();
  if (action === "backup") backup();
});

$("clientName").addEventListener("change", fillClientByName);
$("productSearch").addEventListener("change", fillProductByName);

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/static/service-worker.js?v=20261013-5");
}

loadBootstrap().then(() => {
  setStatus("Rascunho");
  renderItems();
  preview();
});
