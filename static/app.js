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
const tabBtnCity = document.getElementById("tab-btn-city");
const tabPincode = document.getElementById("tab-pincode");
const tabSales = document.getElementById("tab-sales");
const tabNoonUae = document.getElementById("tab-noon-uae");
const tabCity = document.getElementById("tab-city");
const tabBtnPlaceOfSupply = document.getElementById("tab-btn-place-of-supply");
const tabPlaceOfSupply = document.getElementById("tab-place-of-supply");
const posToggleWarehouses = document.getElementById("pos-toggle-warehouses");
const posToggleLocalities = document.getElementById("pos-toggle-localities");
const posCountWarehouses = document.getElementById("pos-count-warehouses");
const posCountLocalities = document.getElementById("pos-count-localities");
const posCountTotal = document.getElementById("pos-count-total");
const posResetBtn = document.getElementById("pos-reset-btn");
const posErrorBanner = document.getElementById("pos-error-banner");
const posMapLoading = document.getElementById("pos-map-loading");
const posFullscreenBtn = document.getElementById("pos-fullscreen-btn");
const posFullscreenLabel = document.getElementById("pos-fullscreen-label");
const posToggleAreas = document.getElementById("pos-toggle-areas");
const posCountAreas = document.getElementById("pos-count-areas");
const cityInputEl = document.getElementById("city-input");
const cityParseCountEl = document.getElementById("city-parse-count");
const cityLookupBtn = document.getElementById("city-lookup-btn");
const cityClearBtn = document.getElementById("city-clear-btn");
const cityCopyBtn = document.getElementById("city-copy-btn");
const cityResultsBody = document.getElementById("city-results-body");
const cityErrorBanner = document.getElementById("city-error-banner");
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
const noonColProductName = document.getElementById("noon-col-product-name");
const noonPlatformTypeFilter = document.getElementById("noon-platform-type-filter");
const noonStartDate = document.getElementById("noon-start-date");
const noonEndDate = document.getElementById("noon-end-date");
const noonConvertBtn = document.getElementById("noon-convert-btn");
const noonClearBtn = document.getElementById("noon-clear-btn");
const noonErrorBanner = document.getElementById("noon-error-banner");
const noonStatus = document.getElementById("noon-status");

let lastResults = [];
let lastCityResults = [];
let selectedSalesFile = null;
let selectedNoonFile = null;
let detectedNoonColumns = [];

const TABS = ["pincode", "sales", "noon-uae", "city", "place-of-supply"];

const TAB_SUBTITLES = {
  pincode:
    "Paste pincodes from Google Sheets, look up city and state, then copy results back into a sheet.",
  sales:
    "Upload a Sales workbook (.xlsx) and download a CSV with the required schema.",
  "noon-uae":
    "Upload a sales CSV, map columns, spread totals across a date range, and download normalized output.",
  city:
    "Paste latitude,longitude pairs, look up city, locality, postcode and state, then copy results back into a sheet.",
  "place-of-supply":
    "Blinkit feeder warehouses and darkstore localities plotted across India. Zoom to split groups, click any point for its details.",
};

const NOON_COLUMN_SELECTS = [
  { el: noonColPlatformType, target: "platform_type" },
  { el: noonColQtySold, target: "qty_sold" },
  { el: noonColRevenue, target: "revenue" },
  { el: noonColItemId, target: "item_id" },
  { el: noonColProductName, target: "product_name" },
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
          <td><span class="status-pill ${statusClass(row.status)}">${escapeHtml(label)}</span></td>
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

function parseCoordinates(text) {
  if (!text.trim()) return [];

  return text
    .split(/[\n\r]+/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function updateCityParseCount() {
  const parsed = parseCoordinates(cityInputEl.value);
  const label = parsed.length === 1 ? "coordinate pair" : "coordinate pairs";
  cityParseCountEl.textContent = `${parsed.length} ${label} parsed`;
}

function showCityError(message) {
  cityErrorBanner.textContent = message;
  cityErrorBanner.classList.remove("hidden");
}

function hideCityError() {
  cityErrorBanner.classList.add("hidden");
  cityErrorBanner.textContent = "";
}

function renderCityResults(results) {
  lastCityResults = results;

  if (!results.length) {
    cityResultsBody.innerHTML = `
      <tr class="empty-row">
        <td colspan="9">Run a lookup to see results</td>
      </tr>`;
    cityCopyBtn.disabled = true;
    return;
  }

  cityResultsBody.innerHTML = results
    .map((row) => {
      const label = STATUS_LABELS[row.status] || row.status;
      const latDisplay = row.latitude || row.input || "";
      return `
        <tr>
          <td class="pincode-col">${escapeHtml(latDisplay)}</td>
          <td>${escapeHtml(row.longitude ?? "")}</td>
          <td>${escapeHtml(row.city ?? "")}</td>
          <td>${escapeHtml(row.locality ?? "")}</td>
          <td>${escapeHtml(row.postcode ?? "")}</td>
          <td>${escapeHtml(row.plus_code ?? "")}</td>
          <td>${escapeHtml(row.principal_subdivision ?? "")}</td>
          <td><span class="status-pill ${statusClass(row.status)}">${escapeHtml(label)}</span></td>
          <td class="details-col">${escapeHtml(row.message ?? "")}</td>
        </tr>`;
    })
    .join("");

  cityCopyBtn.disabled = false;
}

function cityResultsToTsv(results) {
  const lines = [
    "Latitude\tLongitude\tCity\tLocality\tPostcode\tPlus Code\tState\tStatus\tDetails",
  ];
  for (const row of results) {
    const status = STATUS_LABELS[row.status] || row.status;
    lines.push(
      [
        row.latitude || row.input || "",
        row.longitude ?? "",
        row.city ?? "",
        row.locality ?? "",
        row.postcode ?? "",
        row.plus_code ?? "",
        row.principal_subdivision ?? "",
        status,
        row.message ?? "",
      ].join("\t")
    );
  }
  return lines.join("\n");
}

async function runCityLookup() {
  const coordinates = parseCoordinates(cityInputEl.value);
  hideCityError();

  if (!coordinates.length) {
    showCityError("Enter at least one 'latitude,longitude' pair.");
    renderCityResults([]);
    return;
  }

  cityLookupBtn.disabled = true;
  cityLookupBtn.classList.add("loading");

  try {
    const res = await fetch("/api/city/lookup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ coordinates }),
    });

    const data = await res.json().catch(() => ({}));

    if (!res.ok) {
      const detail =
        typeof data.detail === "string"
          ? data.detail
          : Array.isArray(data.detail)
            ? data.detail.map((d) => d.msg || JSON.stringify(d)).join("; ")
            : "Lookup failed";
      showCityError(detail);
      renderCityResults([]);
      return;
    }

    renderCityResults(data.results || []);
  } catch (err) {
    showCityError(err.message || "Network error. Is the server running?");
    renderCityResults([]);
  } finally {
    cityLookupBtn.disabled = false;
    cityLookupBtn.classList.remove("loading");
  }
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
    city: tabBtnCity,
    "place-of-supply": tabBtnPlaceOfSupply,
  };
  const tabPanels = {
    pincode: tabPincode,
    sales: tabSales,
    "noon-uae": tabNoonUae,
    city: tabCity,
    "place-of-supply": tabPlaceOfSupply,
  };

  for (const name of TABS) {
    const isActive = name === tabName;
    tabButtons[name].classList.toggle("active", isActive);
    tabPanels[name].classList.toggle("hidden", !isActive);
  }

  subtitleEl.textContent = TAB_SUBTITLES[tabName];

  if (tabName === "place-of-supply") {
    activatePlaceOfSupplyMap();
  }
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
  noonPlatformTypeFilter.value = "Minutes";
}

function validateNoonForm() {
  if (!selectedNoonFile || !detectedNoonColumns.length) return false;

  for (const { el } of NOON_COLUMN_SELECTS) {
    if (!el.value) return false;
  }

  if (!noonStartDate.value || !noonEndDate.value) return false;
  if (!noonPlatformTypeFilter.value.trim()) return false;
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
  formData.append("product_name_col", noonColProductName.value);
  formData.append("platform_type_filter", noonPlatformTypeFilter.value.trim());
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
tabBtnCity.addEventListener("click", () => switchTab("city"));
tabBtnPlaceOfSupply.addEventListener("click", () => switchTab("place-of-supply"));

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
noonPlatformTypeFilter.addEventListener("input", updateNoonConvertButton);

noonConvertBtn.addEventListener("click", runNoonConvert);
noonClearBtn.addEventListener("click", clearNoonForm);

cityInputEl.addEventListener("input", updateCityParseCount);
cityInputEl.addEventListener("paste", () => setTimeout(updateCityParseCount, 0));

cityLookupBtn.addEventListener("click", runCityLookup);

cityClearBtn.addEventListener("click", () => {
  cityInputEl.value = "";
  hideCityError();
  updateCityParseCount();
  renderCityResults([]);
});

cityCopyBtn.addEventListener("click", async () => {
  if (!lastCityResults.length) return;
  try {
    await copyToClipboard(cityResultsToTsv(lastCityResults));
    showToast("Copied!");
  } catch {
    showCityError("Could not copy to clipboard.");
  }
});

updateParseCount();
updateCityParseCount();

/* ---------------------------------------------------------------------------
   PlaceOfSupply Blinkit map
   --------------------------------------------------------------------------- */

const POS_COLORS = { warehouse: "#d97706", locality: "#0e8f68" };
const POS_INDIA_BOUNDS = [
  [6.5, 68.0],
  [35.7, 97.5],
];

let posMap = null;
let posClusterGroup = null;
let posMarkers = { warehouse: [], locality: [] };
let posDataBounds = null;
let posLoadStarted = false;
let posPlaces = [];
let posHullLayer = null;
let posLinkLayer = null;
let posLocalitiesByPlace = {};

// Hull tints for the place-of-supply areas; cycled by index. Kept away from
// the amber/green used for the point markers themselves.
const POS_AREA_PALETTE = [
  "#2563eb", "#db2777", "#7c3aed", "#0891b2", "#dc2626",
  "#4f46e5", "#c026d3", "#0d9488", "#9333ea", "#b45309",
];

function showPosError(message) {
  posErrorBanner.textContent = message;
  posErrorBanner.classList.remove("hidden");
}

function hidePosError() {
  posErrorBanner.classList.add("hidden");
  posErrorBanner.textContent = "";
}

function posDotIcon(kind) {
  return L.divIcon({
    className: "",
    html: `<div class="pos-dot ${kind}"></div>`,
    iconSize: [13, 13],
    iconAnchor: [6.5, 6.5],
    popupAnchor: [0, -7],
  });
}

function posPopupHtml(kind, rows) {
  const body = rows
    .map(
      ([label, value, mono]) =>
        `<dt>${escapeHtml(label)}</dt><dd${mono ? ' class="mono"' : ""}>${escapeHtml(
          value || "—"
        )}</dd>`
    )
    .join("");
  const kindLabel = kind === "warehouse" ? "Warehouse" : "Locality";
  return `<div class="pos-popup"><span class="pos-popup-kind ${kind}">${kindLabel}</span><dl>${body}</dl></div>`;
}

function buildPosMarkers(data) {
  const warehouseIcon = posDotIcon("warehouse");
  const localityIcon = posDotIcon("locality");

  const warehouses = data.warehouses.map((row) => {
    const marker = L.marker([row.lat, row.lon], {
      icon: warehouseIcon,
      kind: "warehouse",
      title: row.name,
    });
    marker.bindPopup(
      posPopupHtml("warehouse", [
        ["dc_blinkit_warehouse_id", row.id, true],
        ["warehouse", row.name, false],
        ["place_of_supply", row.pos, true],
      ])
    );
    return marker;
  });

  const localities = data.localities.map((row) => {
    const marker = L.marker([row.lat, row.lon], {
      icon: localityIcon,
      kind: "locality",
      title: row.store_name,
    });
    marker.bindPopup(
      posPopupHtml("locality", [
        ["store_id", row.store_id, true],
        ["store_name", row.store_name, false],
        ["dc_blinkit_internal_city", row.city, false],
        ["place_of_supply", row.pos, true],
        ["distance_to_supply", `${row.dist_km} km`, true],
      ])
    );
    return marker;
  });

  return { warehouse: warehouses, locality: localities };
}

// Cluster icon: a ring split by warehouse / locality composition, count inside.
function posClusterIcon(cluster) {
  const children = cluster.getAllChildMarkers();
  let warehouseCount = 0;
  for (const child of children) {
    if (child.options.kind === "warehouse") warehouseCount += 1;
  }

  const total = children.length;
  const localityCount = total - warehouseCount;
  const warehouseDeg = (warehouseCount / total) * 360;

  let ring;
  if (warehouseCount === 0) {
    ring = POS_COLORS.locality;
  } else if (localityCount === 0) {
    ring = POS_COLORS.warehouse;
  } else {
    ring = `conic-gradient(${POS_COLORS.warehouse} 0deg ${warehouseDeg}deg, ${POS_COLORS.locality} ${warehouseDeg}deg 360deg)`;
  }

  // Icon diameter is kept well under maxClusterRadius so two neighbouring
  // cluster rings can never overlap each other at any zoom level.
  let size = 32;
  let sizeClass = "";
  if (total >= 1000) {
    size = 44;
    sizeClass = " lg";
  } else if (total >= 100) {
    size = 40;
    sizeClass = " lg";
  } else if (total >= 10) {
    size = 36;
  }

  return L.divIcon({
    className: `pos-cluster${sizeClass}`,
    html: `<div class="pos-cluster-ring" style="background:${ring}"><div class="pos-cluster-inner">${total}</div></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function posClearLinks() {
  if (posLinkLayer) posLinkLayer.clearLayers();
}

function posDrawLinks(place, color) {
  posClearLinks();
  const members = posLocalitiesByPlace[place.id] || [];
  for (const member of members) {
    L.polyline(
      [
        [place.lat, place.lon],
        [member.lat, member.lon],
      ],
      {
        color,
        weight: 1.2,
        opacity: 0.5,
        interactive: false,
        // Long hauls (label-based or no-warehouse cities) drawn dashed so
        // they read as inferred rather than local.
        dashArray: member.dist_km > 50 ? "5 6" : null,
      }
    ).addTo(posLinkLayer);
  }
}

function posPlacePopupHtml(place, color) {
  const rows = [
    ["place_of_supply", place.id, true],
    ["cities", place.name, false],
    ["warehouses", String(place.warehouse_count), true],
    ["darkstores", String(place.locality_count), true],
    ["median_distance", `${place.median_km} km`, true],
    ["max_distance", `${place.max_km} km`, true],
  ];
  if (place.remote_count > 0) {
    rows.push(["remote_darkstores", `${place.remote_count} beyond 50 km`, true]);
  }
  const body = rows
    .map(
      ([label, value, mono]) =>
        `<dt>${escapeHtml(label)}</dt><dd${mono ? ' class="mono"' : ""}>${escapeHtml(value)}</dd>`
    )
    .join("");
  return `<div class="pos-popup"><span class="pos-popup-kind place" style="background:${color}1f;color:${color}">Place of supply</span><dl>${body}</dl></div>`;
}

function buildPosPlaces(data) {
  posPlaces = data.places;
  posLocalitiesByPlace = {};
  for (const locality of data.localities) {
    (posLocalitiesByPlace[locality.pos] ||= []).push(locality);
  }

  posHullLayer = L.layerGroup();
  posPlaces.forEach((place, index) => {
    const color = POS_AREA_PALETTE[index % POS_AREA_PALETTE.length];
    const style = {
      color,
      weight: 1.5,
      opacity: 0.65,
      fillColor: color,
      fillOpacity: 0.07,
    };
    const shape =
      place.area && place.area.length >= 3
        ? L.polygon(place.area, style)
        : L.circle([place.lat, place.lon], { ...style, radius: 900, fillOpacity: 0.15 });

    shape.bindTooltip(
      `${place.id} · ${place.warehouse_count} WH · ${place.locality_count} darkstores`,
      { sticky: true }
    );
    shape.bindPopup(posPlacePopupHtml(place, color));
    shape.on("popupopen", () => posDrawLinks(place, color));
    shape.on("popupclose", posClearLinks);
    shape.addTo(posHullLayer);
  });

  posCountAreas.textContent = posPlaces.length.toLocaleString();
  if (posToggleAreas.checked) posMap.addLayer(posHullLayer);
}

function refreshPosAreas() {
  if (!posHullLayer) return;
  if (posToggleAreas.checked) {
    posMap.addLayer(posHullLayer);
  } else {
    posClearLinks();
    posMap.removeLayer(posHullLayer);
  }
}

function refreshPosLayers() {
  if (!posClusterGroup) return;

  const showWarehouses = posToggleWarehouses.checked;
  const showLocalities = posToggleLocalities.checked;

  const active = [];
  if (showWarehouses) active.push(...posMarkers.warehouse);
  if (showLocalities) active.push(...posMarkers.locality);

  posClusterGroup.clearLayers();
  posClusterGroup.addLayers(active);

  posCountWarehouses.textContent = posMarkers.warehouse.length.toLocaleString();
  posCountLocalities.textContent = posMarkers.locality.length.toLocaleString();
  const placeSuffix = posPlaces.length ? ` · ${posPlaces.length} places` : "";
  posCountTotal.textContent = `${active.length.toLocaleString()} of ${(
    posMarkers.warehouse.length + posMarkers.locality.length
  ).toLocaleString()} points plotted${placeSuffix}`;
}

// Safari still only exposes the webkit-prefixed fullscreen API.
function fullscreenElement() {
  return document.fullscreenElement || document.webkitFullscreenElement || null;
}

function isPosFullscreen() {
  const el = fullscreenElement();
  return !!el && el === document.querySelector(".map-panel");
}

function syncPosFullscreenBtn() {
  const active = isPosFullscreen();
  posFullscreenLabel.textContent = active ? "Exit fullscreen" : "Fullscreen";
  posFullscreenBtn.setAttribute("aria-pressed", active ? "true" : "false");
}

function togglePosFullscreen() {
  if (isPosFullscreen()) {
    const exit = document.exitFullscreen || document.webkitExitFullscreen;
    if (exit) exit.call(document);
    return;
  }

  const panel = document.querySelector(".map-panel");
  const request = panel.requestFullscreen || panel.webkitRequestFullscreen;
  if (!request) {
    showPosError("Fullscreen is not supported in this browser.");
    return;
  }

  Promise.resolve(request.call(panel)).catch(() => {
    showPosError("Could not enter fullscreen.");
  });
}

function resetPosView() {
  if (!posMap) return;
  posMap.fitBounds(posDataBounds || POS_INDIA_BOUNDS, { padding: [24, 24] });
}

function initPosMap() {
  posMap = L.map("pos-map", {
    maxZoom: 19,
    minZoom: 3,
    // Fractional zoom steps let fitBounds sit snugly around India instead of
    // rounding down a whole level and leaving most of the frame empty.
    zoomSnap: 0.25,
    zoomDelta: 0.5,
    worldCopyJump: false,
  }).fitBounds(POS_INDIA_BOUNDS);

  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution:
      '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>',
    subdomains: "abcd",
    maxZoom: 19,
  }).addTo(posMap);

  // One mixed group so a warehouse and a locality can never be drawn on top of
  // each other: overlapping points merge into a single ring, and points that
  // share an exact coordinate spiderfy apart instead of stacking.
  posClusterGroup = L.markerClusterGroup({
    chunkedLoading: true,
    maxClusterRadius: 70,
    showCoverageOnHover: false,
    zoomToBoundsOnClick: true,
    spiderfyOnMaxZoom: true,
    spiderfyDistanceMultiplier: 1.6,
    iconCreateFunction: posClusterIcon,
    spiderLegPolylineOptions: { weight: 1.5, color: "#6f6d87", opacity: 0.6 },
  });

  posMap.addLayer(posClusterGroup);

  posLinkLayer = L.layerGroup().addTo(posMap);

  posToggleWarehouses.addEventListener("change", refreshPosLayers);
  posToggleLocalities.addEventListener("change", refreshPosLayers);
  posToggleAreas.addEventListener("change", refreshPosAreas);
  posResetBtn.addEventListener("click", resetPosView);
  posFullscreenBtn.addEventListener("click", togglePosFullscreen);

  // The panel changes size on enter and on exit, so Leaflet has to re-measure
  // both times or the tile grid is left cropped or padded out.
  for (const evt of ["fullscreenchange", "webkitfullscreenchange"]) {
    document.addEventListener(evt, () => {
      syncPosFullscreenBtn();
      requestAnimationFrame(() => posMap.invalidateSize());
    });
  }
}

async function loadPosData() {
  hidePosError();

  try {
    const response = await fetch("/api/place-of-supply/points");
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || `Request failed (${response.status})`);
    }

    const data = await response.json();
    posMarkers = buildPosMarkers(data);

    const all = [...posMarkers.warehouse, ...posMarkers.locality];
    if (all.length) {
      posDataBounds = L.latLngBounds(all.map((m) => m.getLatLng()));
    }

    buildPosPlaces(data);
    refreshPosLayers();
    resetPosView();
    posMapLoading.classList.add("hidden");
  } catch (error) {
    posMapLoading.classList.add("hidden");
    posCountTotal.textContent = "No points loaded";
    showPosError(`Could not load map data. ${error.message}`);
  }
}

function activatePlaceOfSupplyMap() {
  if (typeof L === "undefined") {
    posMapLoading.classList.add("hidden");
    showPosError("Map library failed to load. Check your network connection and reload.");
    return;
  }

  if (!posMap) {
    initPosMap();
  }

  // The panel is display:none until now, so Leaflet sized itself against a
  // zero-height container. Re-measure once the panel is actually visible.
  requestAnimationFrame(() => posMap.invalidateSize());

  if (!posLoadStarted) {
    posLoadStarted = true;
    loadPosData();
  }
}
