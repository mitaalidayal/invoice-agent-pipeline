interface ExtractedItem {
  name: string;
  qty: number;
  unit_price: number;
}

interface Extracted {
  vendor: string;
  amount: number;
  items: ExtractedItem[];
  due_date: string | null;
  currency: string;
}

interface ValidationItem {
  name: string;
  qty: number;
  verdict: "ok" | "stock_mismatch" | "unknown_item" | "data_integrity_issue";
  available_qty: number | null;
}

interface PriceNote {
  name: string;
  invoice_unit_price: number;
  expected_unit_price: number;
  deviation_pct: number;
}

interface Validation {
  items: ValidationItem[];
  price_notes: PriceNote[];
  vendor_approved: boolean;
  validation_passed: boolean;
}

interface LogEntry {
  node: string;
  timestamp: string;
  output: { error?: string; flags?: string[] } & Record<string, unknown>;
}

interface PipelineResult {
  extracted: Extracted;
  extraction_failed: boolean;
  validation: Validation;
  approval_decision: "approved" | "rejected" | "pending_review";
  approval_reasoning: string;
  payment_result: { status: string } | null;
  log: LogEntry[];
}

const FORMAT_LABELS: Record<string, string> = { txt: "txt", json: "json", csv: "csv", xml: "xml", pdf: "pdf" };
const DECISION_LABELS: Record<string, string> = { approved: "Approved", rejected: "Rejected", pending_review: "Pending Review" };
const FLAG_LABELS: Record<string, string> = {
  high_value: "Amount exceeds $10,000",
  unapproved_vendor: "Vendor not on approved list",
  validation_failed: "Failed inventory validation",
  non_usd: "Non-USD currency",
};

const appEl = document.getElementById("app") as HTMLDivElement;
const invoiceListEl = document.getElementById("invoice-list") as HTMLUListElement;
const rowCountEl = document.getElementById("row-count") as HTMLElement;
const searchInputEl = document.getElementById("search-input") as HTMLInputElement;
const filterChipsEl = document.getElementById("filter-chips") as HTMLElement;
const panelRightEl = document.getElementById("panel-right") as HTMLElement;
const dropzoneEl = document.getElementById("dropzone") as HTMLElement;
const fileInputEl = document.getElementById("file-input") as HTMLInputElement;
const submitBtnEl = document.getElementById("submit-btn") as HTMLButtonElement;

const SUPPORTED_EXTENSIONS = ["txt", "json", "csv", "xml", "pdf"];
const MAX_UPLOAD_BYTES = 5 * 1024 * 1024; // 5 MB - matches the server-side limit in api.py

let allInvoices: string[] = [];
let activeFormat = "all";
let searchTerm = "";
let selectedInvoice: string | null = null;

function extensionOf(name: string): string {
  return name.slice(name.lastIndexOf(".") + 1).toLowerCase();
}

function escapeHtml(value: string): string {
  const div = document.createElement("div");
  div.textContent = value;
  return div.innerHTML;
}

async function loadInvoices(): Promise<void> {
  const res = await fetch("/api/invoices");
  const data: { invoices: string[] } = await res.json();
  allInvoices = data.invoices;
  renderInvoiceList();
}

function renderInvoiceList(): void {
  const filtered = allInvoices.filter((name) => {
    const matchesFormat = activeFormat === "all" || extensionOf(name) === activeFormat;
    const matchesSearch = name.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesFormat && matchesSearch;
  });

  rowCountEl.textContent = String(filtered.length);
  invoiceListEl.innerHTML = "";

  if (filtered.length === 0) {
    const li = document.createElement("li");
    li.className = "no-matches";
    li.textContent = "No invoices match.";
    invoiceListEl.appendChild(li);
    return;
  }

  for (const name of filtered) {
    const fmt = extensionOf(name);
    const li = document.createElement("li");
    li.className = "invoice-item" + (name === selectedInvoice ? " active" : "");
    li.innerHTML = `<span class="fmt-tag fmt-${fmt}">${FORMAT_LABELS[fmt] ?? fmt}</span><span class="invoice-name"></span>`;
    li.querySelector(".invoice-name")!.textContent = name;
    li.addEventListener("click", () => selectInvoice(name));
    invoiceListEl.appendChild(li);
  }
}

searchInputEl.addEventListener("input", () => {
  searchTerm = searchInputEl.value;
  renderInvoiceList();
});

filterChipsEl.addEventListener("click", (event) => {
  const chip = (event.target as HTMLElement).closest(".chip") as HTMLElement | null;
  if (!chip) return;
  filterChipsEl.querySelectorAll(".chip").forEach((el) => el.classList.remove("active"));
  chip.classList.add("active");
  activeFormat = chip.dataset.fmt ?? "all";
  renderInvoiceList();
});

function selectInvoice(name: string): void {
  // Selecting only highlights the row - processing waits for an explicit
  // submit, so browsing the list doesn't accidentally trigger a real,
  // billed pipeline run on every click.
  selectedInvoice = name;
  renderInvoiceList();
  updateSubmitButton();
}

function updateSubmitButton(): void {
  submitBtnEl.disabled = !selectedInvoice;
  submitBtnEl.textContent = selectedInvoice ? `Process ${selectedInvoice}` : "Select an invoice to process";
}

submitBtnEl.addEventListener("click", () => {
  if (!selectedInvoice) return;
  const name = selectedInvoice;
  appEl.classList.remove("entry");
  appEl.classList.add("active");
  runPipeline(name, () => fetch(`/api/invoices/${encodeURIComponent(name)}/process`, { method: "POST" }));
});

function uploadInvoice(file: File): void {
  selectedInvoice = null; // an uploaded file isn't part of the sample list
  renderInvoiceList();
  updateSubmitButton();
  appEl.classList.remove("entry");
  appEl.classList.add("active");

  const ext = extensionOf(file.name);
  if (!SUPPORTED_EXTENSIONS.includes(ext)) {
    panelRightEl.innerHTML = `
      <div class="empty-state error">
        Unsupported file type: <b>.${escapeHtml(ext || "(none)")}</b>.
        Supported formats: ${SUPPORTED_EXTENSIONS.map((e) => `.${e}`).join(", ")}.
      </div>
    `;
    return;
  }

  if (file.size > MAX_UPLOAD_BYTES) {
    const sizeMb = (file.size / (1024 * 1024)).toFixed(1);
    const limitMb = (MAX_UPLOAD_BYTES / (1024 * 1024)).toFixed(0);
    panelRightEl.innerHTML = `
      <div class="empty-state error">
        File is <b>${sizeMb} MB</b>, which exceeds the ${limitMb} MB limit.
      </div>
    `;
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  runPipeline(file.name, () => fetch("/api/upload", { method: "POST", body: formData }));
}

dropzoneEl.addEventListener("click", () => fileInputEl.click());

fileInputEl.addEventListener("change", () => {
  const file = fileInputEl.files?.[0];
  fileInputEl.value = ""; // reset so re-selecting the same file still fires "change"
  if (file) uploadInvoice(file);
});

(["dragenter", "dragover"] as const).forEach((evt) =>
  dropzoneEl.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzoneEl.classList.add("dragover");
  })
);
(["dragleave", "drop"] as const).forEach((evt) =>
  dropzoneEl.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzoneEl.classList.remove("dragover");
  })
);
dropzoneEl.addEventListener("drop", (e) => {
  const file = e.dataTransfer?.files?.[0];
  if (file) uploadInvoice(file);
});

async function runPipeline(displayName: string, request: () => Promise<Response>): Promise<void> {
  panelRightEl.innerHTML = `
    <div class="processing-wrap">
      <div class="proc-file">Running <b>${escapeHtml(displayName)}</b> through the pipeline</div>
      <div class="spinner"></div>
      <div class="proc-log">Ingestion &rarr; Validation &rarr; Approval &rarr; Payment&hellip;</div>
      <div class="proc-note">
        This can take up to a minute &mdash; each stage may involve a real call to
        Grok, including a self-critique pass on the approval decision.
      </div>
    </div>
  `;

  try {
    const res = await request();
    if (!res.ok) {
      const body = await res.json().catch(() => null);
      throw new Error(body?.detail ?? `Request failed with status ${res.status}`);
    }
    const data: PipelineResult = await res.json();
    renderResult(displayName, data);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    panelRightEl.innerHTML = `<div class="empty-state error">Failed to process ${escapeHtml(displayName)}: ${escapeHtml(message)}</div>`;
  }
}

function formatCurrency(amount: number, currency: string): string {
  return `${currency} ${amount.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function renderResult(name: string, data: PipelineResult): void {
  if (data.extraction_failed) {
    const reason = data.log.at(-1)?.output?.error ?? "Unknown error.";
    panelRightEl.innerHTML = `
      <div class="result">
        <div class="result-header">
          <div><div class="vendor-name">${escapeHtml(name)}</div></div>
          <span class="badge badge-rejected">Extraction Failed</span>
        </div>
        <div class="section">
          <h3>Reason</h3>
          <p class="reasoning-box">${escapeHtml(reason)}</p>
        </div>
      </div>
    `;
    return;
  }

  const decisionBadge =
    data.approval_decision === "approved" ? "badge-approved"
    : data.approval_decision === "pending_review" ? "badge-pending"
    : "badge-rejected";
  const validationPill = data.validation.validation_passed
    ? '<span class="pill-pass">PASSED</span>'
    : '<span class="pill-fail">FAILED</span>';

  const reviewFlags = (data.log.find((entry) => entry.node === "approval")?.output?.flags ?? []) as string[];
  const reviewNotice =
    data.approval_decision === "pending_review"
      ? `
        <div class="section">
          <h3>Flagged For Review</h3>
          <ul class="flag-list">
            ${reviewFlags.map((flag) => `<li>${escapeHtml(FLAG_LABELS[flag] ?? flag)}</li>`).join("")}
          </ul>
        </div>
      `
      : "";

  const itemRows = data.validation.items
    .map(
      (item) => `
        <tr>
          <td>${escapeHtml(item.name)}</td>
          <td>${item.qty}</td>
          <td><span class="verdict-${item.verdict}">${item.verdict.replace(/_/g, " ")}</span></td>
          <td>${item.available_qty ?? "&mdash;"}</td>
        </tr>
      `
    )
    .join("");

  const priceNotes = data.validation.price_notes.length
    ? `
      <div class="section">
        <h3>Price Notes</h3>
        <ul class="price-notes">
          ${data.validation.price_notes
            .map(
              (note) => `
                <li>
                  <strong>${escapeHtml(note.name)}</strong>
                  billed $${note.invoice_unit_price.toFixed(2)} vs expected $${note.expected_unit_price.toFixed(2)}
                  <span class="deviation">${note.deviation_pct > 0 ? "+" : ""}${note.deviation_pct}%</span>
                </li>
              `
            )
            .join("")}
        </ul>
      </div>
    `
    : "";

  // The reasoning text is the LLM's own raw approve/reject verdict - it has
  // no concept of the review gate, which is a separate deterministic check
  // applied after the LLM call. So for a pending_review result, that text
  // reads like a final "approved" verdict (e.g. "no issues support
  // rejection") sitting right under an amber "Pending Review" badge. Reframe
  // it as a recommendation rather than relabeling what the model actually said.
  const isPendingReview = data.approval_decision === "pending_review";
  const reasoningHeading = isPendingReview ? "AI Recommendation" : "Approval Reasoning";
  const reasoningBridge = isPendingReview
    ? `<p class="reasoning-bridge">The AI recommended approval below, but this invoice is held for human sign-off because of the flag(s) above.</p>`
    : "";

  const paymentLine = data.payment_result
    ? `<div class="payment-line ok"><span class="dot ok"></span> Payment: <b>${escapeHtml(data.payment_result.status)}</b></div>`
    : data.approval_decision === "pending_review"
    ? `<div class="payment-line pending"><span class="dot pending"></span> Payment: <b>on hold &mdash; awaiting human review</b></div>`
    : `<div class="payment-line fail"><span class="dot fail"></span> Payment: <b>not processed &mdash; invoice rejected</b></div>`;

  panelRightEl.innerHTML = `
    <div class="result">
      <div class="result-header">
        <div>
          <div class="vendor-name">${escapeHtml(data.extracted.vendor || "(no vendor)")}</div>
          <div class="vendor-file">${escapeHtml(name)}</div>
        </div>
        <span class="badge ${decisionBadge}">${DECISION_LABELS[data.approval_decision] ?? data.approval_decision}</span>
      </div>

      ${reviewNotice}

      <div class="summary-grid">
        <div class="summary-cell">
          <span class="label">Amount</span>
          <span class="value">${formatCurrency(data.extracted.amount, data.extracted.currency)}</span>
        </div>
        <div class="summary-cell">
          <span class="label">Due Date</span>
          <span class="value">${escapeHtml(data.extracted.due_date ?? "—")}</span>
        </div>
        <div class="summary-cell">
          <span class="label">Vendor Approved</span>
          <span class="value">${data.validation.vendor_approved ? "Yes" : "No"}</span>
        </div>
        <div class="summary-cell">
          <span class="label">Inventory Check</span>
          ${validationPill}
        </div>
      </div>

      <div class="section">
        <h3>Line Items</h3>
        <table class="items-table">
          <thead><tr><th>Item</th><th>Qty</th><th>Verdict</th><th>Available</th></tr></thead>
          <tbody>${itemRows}</tbody>
        </table>
      </div>

      ${priceNotes}

      <div class="section">
        <h3>${reasoningHeading}</h3>
        ${reasoningBridge}
        <p class="reasoning-box">${escapeHtml(data.approval_reasoning)}</p>
      </div>

      ${paymentLine}
    </div>
  `;
}

loadInvoices();
