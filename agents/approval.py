import os
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()

MODEL = os.environ.get("XAI_MODEL", "grok-4.6")


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    reasoning: str


def _client() -> OpenAI:
    return OpenAI(api_key=os.environ["XAI_API_KEY"], base_url="https://api.x.ai/v1")


def apply_rules(extracted: dict, validation: dict) -> list[str]:
    """Deterministic flags computed before any LLM call. These don't force a
    decision - they're signals the LLM's reasoning has to account for.
    """
    flags = []

    amount = extracted.get("amount")
    if amount is not None and amount > 10_000:
        flags.append("high_value")

    if not validation["validation_passed"]:
        flags.append("validation_failed")

    if not validation["vendor_approved"]:
        flags.append("unapproved_vendor")

    currency = extracted.get("currency")
    if currency is not None and currency != "USD":
        flags.append("non_usd")

    return flags


def _facts_block(extracted: dict, validation: dict, flags: list[str]) -> str:
    """Shared invoice/validation/flags summary for both prompts below. The
    currency display matters here: rendering a bare Python None reads to the
    model as "something is broken," even with no non_usd flag backing it up -
    so a missing currency (which is just a gap in how CSV is parsed, not a
    real defect in the invoice) gets an explicit, non-alarming explanation
    instead of the literal word "None".
    """
    currency = extracted.get("currency")
    currency_display = (
        currency if currency else "not recorded (this invoice format doesn't capture currency - treat as USD, not as a defect)"
    )

    # name+qty only, deliberately - the raw per-unit prices aren't shown here.
    # Showing them let the model attempt its own subtotal-vs-total arithmetic
    # (qty x price, summed) and flag the gap from tax/shipping - fields we
    # don't extract separately - as an "unexplained" defect on an otherwise
    # legitimate invoice. Price signals go through price_notes below instead,
    # which is the deliberately-computed comparison we actually want reasoned
    # about, not raw ingredients for an unintended calculation.
    items_display = [{"name": item["name"], "qty": item["qty"]} for item in extracted.get("items", [])]

    return f"""Invoice details:
- Vendor: {extracted.get("vendor")!r}
- Amount: {extracted.get("amount")} {currency_display}
- Due date: {extracted.get("due_date")}
- Items: {items_display}

Validation results (per-item stock/inventory check):
- Overall passed: {validation["validation_passed"]}
- Per-item verdicts: {validation["items"]}
- Vendor on approved list: {validation["vendor_approved"]}
- Price deviations from expected unit price (informational only - legitimate
  reasons like volume discounts or rush surcharges are common, this is not
  automatically an error): {validation["price_notes"] or "none"}

Note: the invoice Amount may legitimately be higher than a simple sum of
item quantities times unit prices - tax, shipping, and other fees are real
and common on these invoices but are not extracted as separate fields here.
Do not treat a gap between item-level math and the total Amount as a defect
or inconsistency; it is expected and not evidence of anything wrong.

Rule-based flags for this invoice: {flags or "none"}
- "high_value" means the amount exceeds $10,000 and warrants extra scrutiny.
- "validation_failed" means at least one item failed inventory validation
  (unknown item, stock mismatch, or a data integrity issue like negative
  quantity) - this should generally lean toward rejection unless you have a
  clear reason to approve anyway.
- "unapproved_vendor" means this vendor is not on our approved vendor list -
  this is a fraud-relevant identity check, treat it seriously, not as a
  minor administrative gap.
- "non_usd" means the currency is confirmed as something other than USD, so
  the $10,000 threshold may not directly apply - note this as needing
  manual/FX review rather than guessing a conversion.

Write your reasoning in plain, everyday business language for a reader with
no technical background - describe what a flag means in a sentence (e.g.
"this invoice is billed in euros, not dollars") rather than naming it (e.g.
never write "non_usd" or "high_value" verbatim). Keep it to 2-3 sentences
covering only what actually matters for this invoice, not a checklist of
every fact above."""


def draft_decision(extracted: dict, validation: dict, flags: list[str]) -> dict:
    """First-pass approve/reject decision. Flags are given as signals with an
    explanation of what each means, not as hard rules the LLM must obey -
    the rules layer decides what's worth flagging, the LLM decides what it
    means for this specific invoice.
    """
    prompt = f"""You are simulating a VP-level review of an invoice for approval or rejection.

{_facts_block(extracted, validation, flags)}

Decide "approved" or "rejected", and give reasoning grounded in the specific
facts above (not generic boilerplate).
"""

    completion = _client().beta.chat.completions.parse(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format=ApprovalDecision,
        temperature=0,
    )
    return completion.choices[0].message.parsed.model_dump()


MAX_REFLECTIONS = 2

# Flags that hold an otherwise-approved invoice for human review instead of
# letting payment fire automatically. A "rejected" decision never needs this
# gate - payment already doesn't happen for a rejection, so there's nothing
# to hold. Deliberately excludes price-deviation and reflection-disagreement
# signals: those are common enough for legitimate reasons (discounts, rush
# fees, wording changes on confirmation) that gating on them would make
# pending review too noisy to be useful.
NEEDS_REVIEW_FLAGS = {"high_value", "unapproved_vendor", "validation_failed", "non_usd"}


def run_approval(extracted: dict, validation: dict) -> dict:
    """Orchestrates rules + draft + a bounded reflection loop entirely in
    Python - no LangGraph loop-back edge needed, since reflect_on_decision is
    just a function call. Early-exits as soon as two consecutive passes agree
    on the decision label (not exact reasoning text, which is reworded every
    call even in agreement - see reflect_on_decision). Most invoices converge
    after a single reflection pass; a decision that keeps flipping gets a
    second chance to stabilize before the cap forces a stop.
    """
    flags = apply_rules(extracted, validation)
    current = draft_decision(extracted, validation, flags)

    reflection_count = 0
    while reflection_count < MAX_REFLECTIONS:
        reflected = reflect_on_decision(extracted, validation, flags, current)
        reflection_count += 1
        converged = reflected["decision"] == current["decision"]
        current = reflected
        if converged:
            break

    decision = current["decision"]
    if decision == "approved" and NEEDS_REVIEW_FLAGS & set(flags):
        decision = "pending_review"

    return {
        "decision": decision,
        "reasoning": current["reasoning"],
        "reflection_count": reflection_count,
        "flags": flags,
    }


def reflect_on_decision(extracted: dict, validation: dict, flags: list[str], draft: dict) -> dict:
    """Second-pass critique of the draft decision. Whether this actually
    changes anything is computed by the caller comparing draft vs. this
    result - not self-reported by the model, which could get that meta-fact
    wrong even when the underlying decision is fine.
    """
    prompt = f"""You are critiquing a prior VP-level approval decision on this invoice,
checking it for errors or unjustified reasoning before it becomes final.

{_facts_block(extracted, validation, flags)}

Prior decision: {draft["decision"]}
Prior reasoning: {draft["reasoning"]}

Critically review this decision against the facts above. If it is correct and
well-justified, confirm it with the same decision. If you find an error, an
inconsistency, or a consideration the prior reasoning missed, revise the
decision and explain specifically what changed and why.
"""

    completion = _client().beta.chat.completions.parse(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_format=ApprovalDecision,
        temperature=0,
    )
    return completion.choices[0].message.parsed.model_dump()
