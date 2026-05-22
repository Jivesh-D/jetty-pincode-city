const inputEl = document.getElementById("pincode-input");
const parseCountEl = document.getElementById("parse-count");
const lookupBtn = document.getElementById("lookup-btn");
const clearBtn = document.getElementById("clear-btn");
const copyBtn = document.getElementById("copy-btn");
const resultsBody = document.getElementById("results-body");
const errorBanner = document.getElementById("error-banner");
const toast = document.getElementById("toast");

let lastResults = [];

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

function showToast() {
  toast.classList.remove("hidden");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => toast.classList.add("hidden"), 2000);
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
    showToast();
  } catch {
    showError("Could not copy to clipboard.");
  }
});

updateParseCount();
