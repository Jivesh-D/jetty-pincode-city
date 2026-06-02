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
const tabPincode = document.getElementById("tab-pincode");
const tabSales = document.getElementById("tab-sales");
const salesFileInput = document.getElementById("sales-file-input");
const salesFileInfo = document.getElementById("sales-file-info");
const salesConvertBtn = document.getElementById("sales-convert-btn");
const salesClearBtn = document.getElementById("sales-clear-btn");
const salesErrorBanner = document.getElementById("sales-error-banner");
const salesStatus = document.getElementById("sales-status");

let lastResults = [];
let selectedSalesFile = null;

const TAB_SUBTITLES = {
  pincode:
    "Paste pincodes from Google Sheets, look up city and state, then copy results back into a sheet.",
  sales:
    "Upload a Sales workbook (.xlsx) and download a CSV with the required schema.",
};

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
  const isPincode = tabName === "pincode";
  tabBtnPincode.classList.toggle("active", isPincode);
  tabBtnSales.classList.toggle("active", !isPincode);
  tabPincode.classList.toggle("hidden", !isPincode);
  tabSales.classList.toggle("hidden", isPincode);
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

updateParseCount();
