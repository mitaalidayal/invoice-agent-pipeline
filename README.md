# Invoice Processing Agent

A multi-agent invoice processing pipeline built for the Galatiq / Acme Corp case study. It automates ingestion, inventory/vendor validation, VP-level approval (with a self-critique loop and a human-in-the-loop gate), and mock payment for invoices arriving as PDFs, text, CSV, JSON, or XML — runnable from the command line or through a web UI.

## Business Impact

Acme Corp's manual process was losing **$2M/year**, with a **30% error rate** and **5-day processing delays**, largely from manual data entry, inconsistent validation against the inventory database, and VP approval over email chains.

This system addresses each directly:

- **Error rate** — every invoice goes through deterministic inventory, vendor, and price checks against `inventory.db`, and the approval decision itself passes through a bounded self-critique (reflection) loop that has to explicitly confirm or revise its own draft before finalizing, rather than a single unchecked LLM call.
- **Processing delays** — a full invoice (extraction → validation → approval → payment) completes in well under a minute, versus days of email back-and-forth, with no loss of an audit trail: every run produces a structured, timestamped log of what each stage decided and why.
- **Stakeholder trust** — full automation of every decision is itself a risk stakeholders would reasonably push back on. Instead of choosing between "fully manual" (slow) and "fully automatic" (risky), invoices that are high-value, from an unapproved vendor, in a foreign currency, or that fail inventory validation are held for a human to sign off before payment — even when the AI itself would have approved them.

## Architecture

Built with **LangGraph** as a 4-stage graph, plus two terminal branches:

```
Ingestion → Validation → Approval → Payment
                              ├──→ Reject          (LLM decision: rejected)
                              └──→ Hold for Review  (approved, but flagged for a human)
```

- **Ingestion** (`agents/ingestion.py`) — native parsers for `.json`/`.csv`/`.xml` (deterministic, no LLM cost for clean structured data), falling back to a Grok extraction call for `.txt`/`.pdf` or any structured file that fails to parse. The Grok prompt handles OCR-corrupted/misspelled item names by mapping them to canonical inventory names, and first judges whether the document is actually an invoice at all — rejecting non-invoice uploads (e.g. a resume) instead of force-extracting fake data.
- **Validation** (`agents/validation.py`) — checks aggregated item quantities against `inventory.db` stock, flags unknown items and data-integrity issues (e.g. negative quantities), checks the vendor against an approved-vendor list, and surfaces unit-price deviations as informational notes (not auto-rejected, since legitimate discounts/surcharges are common in the sample data).
- **Approval** (`agents/approval.py`) — a rules layer computes flags (`high_value`, `validation_failed`, `unapproved_vendor`, `non_usd`) as *signals*, not hard rules; an LLM draft decision reasons over the full picture, then a bounded reflection pass (max 2) critiques and can revise that draft before it's final. If the final decision is "approved" but one of the four flags above is present, it's downgraded to `pending_review` instead of paying automatically — a rejected decision is never held, since payment already doesn't happen for those.
- **Payment** (`agents/payment.py`) — mock payment call, only reached for a clean `approved` decision.

## Setup

```bash
git clone <this-repo-url>
cd galatiq-case-invoices
uv sync
```

Copy `.env.example` to `.env` and fill in your xAI API key:

```bash
cp .env.example .env
```

```
XAI_API_KEY=your_xai_api_key_here
XAI_MODEL=grok-4.6
```

`XAI_MODEL` is optional — it defaults to `grok-4.6` if unset, so you only need to set it to point at a different model.

Seed the local inventory database (drops and recreates `inventory.db` every run, so it's always in sync with the current schema):

```bash
uv run python setup_db.py
```

## Running It

**Command line**, one invoice at a time:

```bash
uv run python main.py --invoice_path=data/invoices/invoice_1001.txt
```

Prints the vendor, validation result, decision, and reasoning, and writes a full structured JSON log to `logs/`.

**Web UI**, a single command:

```bash
uv run python run_app.py
```

Builds the frontend automatically on first run, then serves everything at **http://localhost:8000** — browse and run any sample invoice from `data/invoices/`, or drag-and-drop / upload your own file.

## Testing

```bash
uv run pytest -m "not integration"   # fast, deterministic, no API calls - runs in under a second
uv run pytest                        # full suite, including real Grok API calls (small cost, ~10 minutes)
```

## Above and Beyond

- **Web UI** — FastAPI backend + a vanilla TypeScript/Vite frontend, served together on one port via a single `run_app.py` entrypoint.
- **Unit price and vendor validation** — extending the provided inventory schema, as the brief invites, to catch price deviations and unapproved vendors, not just stock mismatches.
- **Non-invoice guardrail** — a genuinely non-invoice upload (e.g. a resume) is rejected at extraction time instead of being force-parsed into fabricated invoice data.
- **Upload size limit** — uploads are capped at 5MB before any pipeline run is triggered.
- **Human-in-the-loop review gate** — an otherwise-"approved" invoice is held for human sign-off, not paid automatically, when it's high-value, from an unapproved vendor, in a non-USD currency, or fails inventory validation.
- **Full test suite** — a fast, free, deterministic subset covering rules/routing/parsing logic, plus a real-API integration subset that locks in actual LLM behavior (extraction accuracy, reflection catching a bad draft, regression tests for real bugs found via live testing).
