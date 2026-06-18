const state = {
  status: "Rascunho",
  items: [],
  clients: [],
  products: [],
  history: []
};

const $ = (id) => document.getElementById(id);

function moneyValue(value) {
  const text = String(value || "0").trim().replace(/\./g, "").replace(",", ".");
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

function payload() {
  return {
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

function setStatus(status) {
  state.status = status;
  document.querySelectorAll(".status-pill").forEach((button) => {
    button.classList.toggle("active", button.dataset.status === status);
  });
  preview();
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
  descEl.value = "";
  priceEl.value = "";
  costEl.value = "";
  renderItems();
  preview();
}

function addEmptyItem() {
  state.items.push({ description: "", quantity: "1", unit_price: "0", unit_cost: "0", discount: "0" });
  renderItems();
}

function renderItems() {
  const body = $("itemsBody");
  body.innerHTML = "";
  state.items.forEach((item, index) => {
    const subtotal = Math.max(0, moneyValue(item.quantity) * moneyValue(item.unit_price) - moneyValue(item.discount));
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><input data-field="description" data-index="${index}" value="${item.description.replaceAll('"', "&quot;")}"></td>
      <td><input data-field="quantity" data-index="${index}" inputmode="decimal" value="${item.quantity}"></td>
      <td><input data-field="unit_price" data-index="${index}" inputmode="decimal" value="${item.unit_price}"></td>
      <td><input data-field="unit_cost" data-index="${index}" inputmode="decimal" value="${item.unit_cost}"></td>
      <td><input data-field="discount" data-index="${index}" inputmode="decimal" value="${item.discount}"></td>
      <td><strong>${formatBRL(subtotal)}</strong></td>
      <td><button type="button" class="remove" data-remove="${index}">Remover</button></td>
    `;
    body.appendChild(row);
  });
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
    const pdfButton = document.querySelector('[data-action="pdf"]');
    if (pdfButton) {
      pdfButton.disabled = true;
      pdfButton.textContent = "Gerando...";
    }
    const data = await api("/api/quotes", { method: "POST", body: JSON.stringify(payload()) });
    $("pdfStatus").textContent = `PDF gerado: ${data.filename}`;
    $("downloadLink").href = data.download_url;
    $("downloadLink").setAttribute("download", data.filename);
    $("downloadLink").classList.remove("disabled");
    $("whatsappLink").href = data.whatsapp_url;
    $("whatsappLink").classList.remove("disabled");
    state.history = data.history || state.history;
    updateMetrics(data.metrics);
    renderHistory();
    toast("PDF gerado. Use Download ou WhatsApp nos botoes abaixo.");
  } catch (error) {
    toast(error.message);
  } finally {
    const pdfButton = document.querySelector('[data-action="pdf"]');
    if (pdfButton) {
      pdfButton.disabled = false;
      pdfButton.textContent = "Gerar PDF";
    }
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
      <strong>#${row.id}</strong>
      <span>${row.name}<br><small>${row.vehicle || "-"} ${row.plate || ""}</small></span>
      <span>${row.status}</span>
      <span>R$ ${Number(row.total || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 })}</span>
      <button type="button" class="ghost" data-load="${row.id}">Abrir</button>
    </div>
  `).join("");
}

async function openHistoryQuote(id) {
  try {
    const data = await api(`/api/history/${id}`);
    $("clientName").value = data.client_name || "";
    $("phone").value = data.phone || "";
    $("vehicle").value = data.vehicle || "";
    $("plate").value = data.plate || "";
    $("notes").value = data.notes || $("notes").value;
    setStatus(data.status || "Rascunho");
    state.items = data.items.map((item) => ({
      description: item.description,
      quantity: item.quantity,
      unit_price: item.unit_price,
      unit_cost: item.unit_cost,
      discount: item.discount
    }));
    renderItems();
    preview();
    $("historyPanel").hidden = true;
  } catch (error) {
    toast(error.message);
  }
}

function resetForm() {
  $("clientName").value = "";
  $("phone").value = "";
  $("vehicle").value = "";
  $("plate").value = "";
  $("taxRate").value = "0";
  $("notes").value = "Validade da proposta: 7 dias. Pagamento conforme combinado. Pecas sujeitas a disponibilidade.";
  $("includeCover").checked = true;
  $("pdfStatus").textContent = "Nenhum PDF gerado nesta sessao.";
  $("downloadLink").classList.add("disabled");
  $("whatsappLink").classList.add("disabled");
  state.items = [];
  setStatus("Rascunho");
  addEmptyItem();
  preview();
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
  state.history = data.history || [];
  fillDatalists();
  updateMetrics(data.metrics);
  renderHistory();
}

document.addEventListener("input", (event) => {
  const target = event.target;
  if (target.dataset && target.dataset.field) {
    const item = state.items[Number(target.dataset.index)];
    item[target.dataset.field] = target.value;
    const subtotal = Math.max(0, moneyValue(item.quantity) * moneyValue(item.unit_price) - moneyValue(item.discount));
    const totalCell = target.closest("tr").querySelector("td:nth-child(6) strong");
    if (totalCell) totalCell.textContent = formatBRL(subtotal);
  }
  preview();
});

document.addEventListener("click", (event) => {
  const target = event.target.closest("button, a");
  if (!target) return;
  if (target.id === "downloadLink") downloadPdf(event);
  if (target.dataset.status) setStatus(target.dataset.status);
  if (target.dataset.remove) {
    state.items.splice(Number(target.dataset.remove), 1);
    renderItems();
    preview();
  }
  if (target.dataset.load) openHistoryQuote(target.dataset.load);
  const action = target.dataset.action;
  if (action === "new") resetForm();
  if (action === "history") $("historyPanel").hidden = false;
  if (action === "close-history") $("historyPanel").hidden = true;
  if (action === "report") window.location.href = "/relatorio-mensal";
  if (action === "pdf") generatePdf();
  if (action === "add-service") addItem("service");
  if (action === "add-product") addItem("product");
  if (action === "add-empty") addEmptyItem();
  if (action === "backup") backup();
});

$("clientName").addEventListener("change", fillClientByName);
$("productSearch").addEventListener("change", fillProductByName);

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/static/service-worker.js?v=20260618-5");
}

loadBootstrap().then(() => {
  setStatus("Rascunho");
  addEmptyItem();
  preview();
});
