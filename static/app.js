const inputEl = document.getElementById("pincode-input");
const parseCountEl = document.getElementById("parse-count");
const lookupBtn = document.getElementById("lookup-btn");
const clearBtn = document.getElementById("clear-btn");
const copyBtn = document.getElementById("copy-btn");
const resultsBody = document.getElementById("results-body");
const errorBanner = document.getElementById("error-banner");
const toast = document.getElementById("toast");
const subtitleEl = document.getElementById("subtitle");
const tabBtnPincode = document.getElementById("tab-btn-pincode");
const tabBtnSales = document.getElementById("tab-btn-sales");
const tabBtnNoonUae = document.getElementById("tab-btn-noon-uae");
const tabPincode = document.getElementById("tab-pincode");
const tabSales = document.getElementById("tab-sales");
const tabNoonUae = document.getElementById("tab-noon-uae");
const salesFileInput = document.getElementById("sales-file-input");
const salesFileInfo = document.getElementById("sales-file-info");
const salesConvertBtn = document.getElementById("sales-convert-btn");
const salesClearBtn = document.getElementById("sales-clear-btn");
const salesErrorBanner = document.getElementById("sales-error-banner");
const salesStatus = document.getElementById("sales-status");
const noonFileInput = document.getElementById("noon-file-input");
const noonFileInfo = document.getElementById("noon-file-info");
const noonMappingSection = document.getElementById("noon-mapping-section");
const noonColPlatformType = document.getElementById("noon-col-platform-type");
const noonColQtySold = document.getElementById("noon-col-qty-sold");
const noonColRevenue = document.getElementById("noon-col-revenue");
const noonColItemId = document.getElementById("noon-col-item-id");
const noonStartDate = document.getElementById("noon-start-date");
const noonEndDate = document.getElementById("noon-end-date");
const noonConvertBtn = document.getElementById("noon-convert-btn");
const noonClearBtn = document.getElementById("noon-clear-btn");
const noonErrorBanner = document.getElementById("noon-error-banner");
const noonStatus = document.getElementById("noon-status");

let lastResults = [];
let selectedSalesFile = null;
let selectedNoonFile = null;
let detectedNoonColumns = [];

const TABS = ["pincode", "sales", "noon-uae"];

const TAB_SUBTITLES = {
  pincode:
    "Paste pincodes from Google Sheets, look up city and state, then copy results back into a sheet.",
  sales:
    "Upload a Sales workbook (.xlsx) and download a CSV with the required schema.",
  "noon-uae":
    "Upload a sales CSV, map columns, spread totals across a date range, and download normalized output.",
};

const NOON_COLUMN_SELECTS = [
  { el: noonColPlatformType, target: "platform_type" },
  { el: noonColQtySold, target: "qty_sold" },
  { el: noonColRevenue, target: "revenue" },
  { el: noonColItemId, target: "item_id" },
];

const STATUS_LABELS = {
  ok: "OK",
  not_found: "Not found",
  invalid: "Invalid",
  error: "Error",
};

function parsePincodes(text) {
  if (!text.trim()) return [];

  const tokens = text
    .split(/[\n,\t\r]+/)
    .flatMap((line) => line.trim().split(/\s+/))
    .map((t) => t.trim())
    .filter(Boolean);

  const pincodes = [];
  for (const token of tokens) {
    if (/^\d{6}$/.test(token)) {
      pincodes.push(token);
      continue;
    }

    const digitsOnly = token.replace(/\D/g, "");
    if (/^\d{6}$/.test(digitsOnly) && digitsOnly !== token) {
      pincodes.push(digitsOnly);
      continue;
    }

    if (/^\d+$/.test(token)) {
      pincodes.push(token);
      continue;
    }

    const embedded = token.match(/\d{6}/);
    if (embedded && !/[a-zA-Z]/.test(token)) {
      pincodes.push(embedded[0]);
    } else {
      pincodes.push(token);
    }
  }
  return pincodes;
}

function updateParseCount() {
  const parsed = parsePincodes(inputEl.value);
  const label = parsed.length === 1 ? "pincode" : "pincodes";
  parseCountEl.textContent = `${parsed.length} ${label} parsed`;
}

function showError(message) {
  errorBanner.textContent = message;
  errorBanner.classList.remove("hidden");
}

function hideError() {
  errorBanner.classList.add("hidden");
  errorBanner.textContent = "";
}

function statusClass(status) {
  return `status-${status}`;
}

function renderResults(results) {
  lastResults = results;

  if (!results.length) {
    resultsBody.innerHTML = `
      <tr class="empty-row">
        <td colspan="5">Run a lookup to see results</td>
      </tr>`;
    copyBtn.disabled = true;
    return;
  }

  resultsBody.innerHTML = results
    .map((row) => {
      const label = STATUS_LABELS[row.status] || row.status;
      return `
        <tr>
          <td class="pincode-col">${escapeHtml(row.pincode)}</td>
          <td>${escapeHtml(row.city ?? "")}</td>
          <td>${escapeHtml(row.state ?? "")}</td>
          <td class="${statusClass(row.status)}">${escapeHtml(label)}</td>
          <td class="details-col">${escapeHtml(row.message ?? "")}</td>
        </tr>`;
    })
    .join("");

  copyBtn.disabled = false;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(str) {
  return escapeHtml(str).replace(/'/g, "&#39;");
}

function resultsToTsv(results) {
  const lines = ["Pincode\tCity\tState\tStatus\tDetails"];
  for (const row of results) {
    const status = STATUS_LABELS[row.status] || row.status;
    lines.push(
      [row.pincode, row.city ?? "", row.state ?? "", status, row.message ?? ""].join(
        "\t"
      )
    );
  }
  return lines.join("\n");
}

async function copyToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  document.body.appendChild(ta);
  ta.select();
  document.execCommand("copy");
  document.body.removeChild(ta);
}

function showToast(message = "Copied!") {
  toast.textContent = message;
  toast.classList.remove("hidden");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => toast.classList.add("hidden"), 2000);
}

function switchTab(tabName) {
  const tabButtons = {
    pincode: tabBtnPincode,
    sales: tabBtnSales,
    "noon-uae": tabBtnNoonUae,
  };
  const tabPanels = {
    pincode: tabPincode,
    sales: tabSales,
    "noon-uae": tabNoonUae,
  };

  for (const name of TABS) {
    const isActive = name === tabName;
    tabButtons[name].classList.toggle("active", isActive);
    tabPanels[name].classList.toggle("hidden", !isActive);
  }

  subtitleEl.textContent = TAB_SUBTITLES[tabName];
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function showSalesError(message) {
  salesErrorBanner.textContent = message;
  salesErrorBanner.classList.remove("hidden");
}

function hideSalesError() {
  salesErrorBanner.classList.add("hidden");
  salesErrorBanner.textContent = "";
}

function hideSalesStatus() {
  salesStatus.classList.add("hidden");
  salesStatus.textContent = "";
}

function showSalesStatus(message) {
  salesStatus.textContent = message;
  salesStatus.classList.remove("hidden");
}

function updateSalesFileInfo() {
  if (!selectedSalesFile) {
    salesFileInfo.textContent = "No file selected";
    salesConvertBtn.disabled = true;
    return;
  }

  salesFileInfo.textContent = `${selectedSalesFile.name} (${formatFileSize(selectedSalesFile.size)})`;
  salesConvertBtn.disabled = false;
}

function parseContentDispositionFilename(headerValue) {
  if (!headerValue) return "sales.csv";

  const utf8Match = headerValue.match(/filename\*=UTF-8''([^;]+)/i);
  if (utf8Match) {
    return decodeURIComponent(utf8Match[1]);
  }

  const plainMatch = headerValue.match(/filename="?([^";]+)"?/i);
  return plainMatch ? plainMatch[1] : "sales.csv";
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

async function runSalesConvert() {
  if (!selectedSalesFile) {
    showSalesError("Choose an .xlsx file first.");
    return;
  }

  hideSalesError();
  hideSalesStatus();
  salesConvertBtn.disabled = true;
  salesConvertBtn.classList.add("loading");

  const formData = new FormData();
  formData.append("file", selectedSalesFile);

  try {
    const res = await fetch("/api/sales/convert", {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      const detail =
        typeof data.detail === "string"
          ? data.detail
          : Array.isArray(data.detail)
            ? data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
            : "Conversion failed";
      showSalesError(detail);
      return;
    }

    const blob = await res.blob();
    const filename = parseContentDispositionFilename(
      res.headers.get("Content-Disposition")
    );
    const csvText = await blob.text();
    const rowCount = Math.max(0, csvText.trim().split("\n").length - 1);

    downloadBlob(new Blob([csvText], { type: "text/csv" }), filename);
    showSalesStatus(`Download started — ${rowCount} data rows in CSV.`);
    showToast("CSV downloaded");
  } catch (err) {
    showSalesError(err.message || "Network error. Is the server running?");
  } finally {
    salesConvertBtn.disabled = !selectedSalesFile;
    salesConvertBtn.classList.remove("loading");
  }
}

function showNoonError(message) {
  noonErrorBanner.textContent = message;
  noonErrorBanner.classList.remove("hidden");
}

function hideNoonError() {
  noonErrorBanner.classList.add("hidden");
  noonErrorBanner.textContent = "";
}

function hideNoonStatus() {
  noonStatus.classList.add("hidden");
  noonStatus.textContent = "";
}

function showNoonStatus(message) {
  noonStatus.textContent = message;
  noonStatus.classList.remove("hidden");
}

function populateNoonSelect(selectEl, columns, preferredName) {
  selectEl.innerHTML = '<option value="">Select column…</option>';
  for (const col of columns) {
    const option = document.createElement("option");
    option.value = col;
    option.textContent = col;
    selectEl.appendChild(option);
  }
  if (preferredName && columns.includes(preferredName)) {
    selectEl.value = preferredName;
  }
  selectEl.disabled = false;
}

function resetNoonMapping() {
  detectedNoonColumns = [];
  noonMappingSection.classList.add("hidden");
  for (const { el } of NOON_COLUMN_SELECTS) {
    el.innerHTML = '<option value="">Select column…</option>';
    el.value = "";
    el.disabled = true;
  }
  noonStartDate.value = "";
  noonEndDate.value = "";
}

function validateNoonForm() {
  if (!selectedNoonFile || !detectedNoonColumns.length) return false;

  for (const { el } of NOON_COLUMN_SELECTS) {
    if (!el.value) return false;
  }

  if (!noonStartDate.value || !noonEndDate.value) return false;
  if (noonEndDate.value < noonStartDate.value) return false;

  return true;
}

function updateNoonFileInfo() {
  if (!selectedNoonFile) {
    noonFileInfo.textContent = "No file selected";
    noonConvertBtn.disabled = true;
    return;
  }

  noonFileInfo.textContent = `${selectedNoonFile.name} (${formatFileSize(selectedNoonFile.size)})`;
  noonConvertBtn.disabled = !validateNoonForm();
}

function updateNoonConvertButton() {
  noonConvertBtn.disabled = !validateNoonForm();
}

async function fetchNoonHeaders() {
  if (!selectedNoonFile) return;

  hideNoonError();
  hideNoonStatus();
  resetNoonMapping();
  noonFileInfo.textContent = `${selectedNoonFile.name} (${formatFileSize(selectedNoonFile.size)}) — reading columns…`;
  noonConvertBtn.disabled = true;

  const formData = new FormData();
  formData.append("file", selectedNoonFile);

  try {
    const res = await fetch("/api/noon-uae/headers", {
      method: "POST",
      body: formData,
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      const detail =
        typeof data.detail === "string"
          ? data.detail
          : Array.isArray(data.detail)
            ? data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
            : "Could not read CSV headers";
      selectedNoonFile = null;
      noonFileInput.value = "";
      showNoonError(detail);
      updateNoonFileInfo();
      return;
    }

    detectedNoonColumns = data.columns || [];
    if (!detectedNoonColumns.length) {
      selectedNoonFile = null;
      noonFileInput.value = "";
      showNoonError("No columns found in the CSV header row.");
      updateNoonFileInfo();
      return;
    }

    for (const { el, target } of NOON_COLUMN_SELECTS) {
      populateNoonSelect(el, detectedNoonColumns, target);
    }

    noonMappingSection.classList.remove("hidden");
    noonFileInfo.textContent = `${selectedNoonFile.name} (${formatFileSize(selectedNoonFile.size)}) — ${detectedNoonColumns.length} columns detected`;
    updateNoonConvertButton();
  } catch (err) {
    selectedNoonFile = null;
    noonFileInput.value = "";
    showNoonError(err.message || "Network error. Is the server running?");
    updateNoonFileInfo();
  }
}

async function runNoonConvert() {
  if (!validateNoonForm()) {
    if (noonStartDate.value && noonEndDate.value && noonEndDate.value < noonStartDate.value) {
      showNoonError("end_Date must be on or after start_Date.");
    } else {
      showNoonError("Choose a file, map all columns, and set both dates.");
    }
    return;
  }

  hideNoonError();
  hideNoonStatus();
  noonConvertBtn.disabled = true;
  noonConvertBtn.classList.add("loading");

  const formData = new FormData();
  formData.append("file", selectedNoonFile);
  formData.append("platform_type_col", noonColPlatformType.value);
  formData.append("qty_sold_col", noonColQtySold.value);
  formData.append("revenue_col", noonColRevenue.value);
  formData.append("item_id_col", noonColItemId.value);
  formData.append("start_date", noonStartDate.value);
  formData.append("end_date", noonEndDate.value);

  try {
    const res = await fetch("/api/noon-uae/convert", {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      const detail =
        typeof data.detail === "string"
          ? data.detail
          : Array.isArray(data.detail)
            ? data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
            : "Conversion failed";
      showNoonError(detail);
      return;
    }

    const blob = await res.blob();
    const filename = parseContentDispositionFilename(
      res.headers.get("Content-Disposition")
    );
    const csvText = await blob.text();
    const rowCount = Math.max(0, csvText.trim().split("\n").length - 1);

    downloadBlob(new Blob([csvText], { type: "text/csv" }), filename);
    showNoonStatus(`Download started — ${rowCount} data rows in CSV.`);
    showToast("CSV downloaded");
  } catch (err) {
    showNoonError(err.message || "Network error. Is the server running?");
  } finally {
    noonConvertBtn.disabled = !validateNoonForm();
    noonConvertBtn.classList.remove("loading");
  }
}

function clearNoonForm() {
  selectedNoonFile = null;
  noonFileInput.value = "";
  hideNoonError();
  hideNoonStatus();
  resetNoonMapping();
  updateNoonFileInfo();
}

async function runLookup() {
  const pincodes = parsePincodes(inputEl.value);
  hideError();

  if (!pincodes.length) {
    showError("Enter at least one valid 6-digit pincode.");
    renderResults([]);
    return;
  }

  lookupBtn.disabled = true;
  lookupBtn.classList.add("loading");

  try {
    const res = await fetch("/api/pincodes/lookup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pincodes }),
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      const detail =
        typeof data.detail === "string"
          ? data.detail
          : Array.isArray(data.detail)
            ? data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
            : "Lookup failed";
      showError(detail);
      renderResults([]);
      return;
    }

    renderResults(data.results || []);
  } catch (err) {
    showError(err.message || "Network error. Is the server running?");
    renderResults([]);
  } finally {
    lookupBtn.disabled = false;
    lookupBtn.classList.remove("loading");
  }
}

inputEl.addEventListener("input", updateParseCount);
inputEl.addEventListener("paste", () => setTimeout(updateParseCount, 0));

lookupBtn.addEventListener("click", runLookup);

clearBtn.addEventListener("click", () => {
  inputEl.value = "";
  hideError();
  updateParseCount();
  renderResults([]);
});

copyBtn.addEventListener("click", async () => {
  if (!lastResults.length) return;
  try {
    await copyToClipboard(resultsToTsv(lastResults));
    showToast("Copied!");
  } catch {
    showError("Could not copy to clipboard.");
  }
});

tabBtnPincode.addEventListener("click", () => switchTab("pincode"));
tabBtnSales.addEventListener("click", () => switchTab("sales"));
tabBtnNoonUae.addEventListener("click", () => switchTab("noon-uae"));

salesFileInput.addEventListener("change", () => {
  hideSalesError();
  hideSalesStatus();
  selectedSalesFile = salesFileInput.files?.[0] || null;

  if (selectedSalesFile && !selectedSalesFile.name.toLowerCase().endsWith(".xlsx")) {
    selectedSalesFile = null;
    salesFileInput.value = "";
    showSalesError("Please choose an .xlsx file.");
  }

  updateSalesFileInfo();
});

salesConvertBtn.addEventListener("click", runSalesConvert);

salesClearBtn.addEventListener("click", () => {
  selectedSalesFile = null;
  salesFileInput.value = "";
  hideSalesError();
  hideSalesStatus();
  updateSalesFileInfo();
});

noonFileInput.addEventListener("change", () => {
  hideNoonError();
  hideNoonStatus();
  selectedNoonFile = noonFileInput.files?.[0] || null;

  if (selectedNoonFile && !selectedNoonFile.name.toLowerCase().endsWith(".csv")) {
    selectedNoonFile = null;
    noonFileInput.value = "";
    showNoonError("Please choose a .csv file.");
    clearNoonForm();
    return;
  }

  if (selectedNoonFile) {
    fetchNoonHeaders();
  } else {
    clearNoonForm();
  }
});

for (const { el } of NOON_COLUMN_SELECTS) {
  el.addEventListener("change", updateNoonConvertButton);
}

noonStartDate.addEventListener("change", updateNoonConvertButton);
noonEndDate.addEventListener("change", updateNoonConvertButton);

noonConvertBtn.addEventListener("click", runNoonConvert);
noonClearBtn.addEventListener("click", clearNoonForm);

updateParseCount();
