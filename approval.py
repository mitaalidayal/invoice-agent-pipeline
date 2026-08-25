import os
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()


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

    if extracted.get("currency") != "USD":
        flags.append("non_usd")

    return flags


def draft_decision(extracted: dict, validation: dict, flags: list[str]) -> dict:
    """First-pass approve/reject decision. Flags are given as signals with an
    explanation of what each means, not as hard rules the LLM must obey -
    the rules layer decides what's worth flagging, the LLM decides what it
    means for this specific invoice.
    """
    prompt = f"""You are simulating a VP-level review of an invoice for approval or rejection.

Invoice details:
- Vendor: {extracted.get("vendor")!r}
- Amount: {extracted.get("amount")} {extracted.get("currency")}
- Due date: {extracted.get("due_date")}
- Items: {extracted.get("items")}

Validation results (per-item stock/inventory check):
- Overall passed: {validation["validation_passed"]}
- Per-item verdicts: {validation["items"]}

Rule-based flags for this invoice: {flags or "none"}
- "high_value" means the amount exceeds $10,000 and warrants extra scrutiny.
- "validation_failed" means at least one item failed inventory validation
  (unknown item, stock mismatch, or a data integrity issue like negative
  quantity) - this should generally lean toward rejection unless you have a
  clear reason to approve anyway.
- "non_usd" means the currency isn't confirmed as USD, so the $10,000
  threshold may not directly apply - note this as needing manual/FX review
  rather than guessing a conversion.

Decide "approved" or "rejected", and give reasoning grounded in the specific
facts above (not generic boilerplate).
"""

    completion = _client().beta.chat.completions.parse(
        model="grok-4.6",
        messages=[{"role": "user", "content": prompt}],
        response_format=ApprovalDecision,
    )
    return completion.choices[0].message.parsed.model_dump()


MAX_REFLECTIONS = 2


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

    return {
        "decision": current["decision"],
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

Invoice details:
- Vendor: {extracted.get("vendor")!r}
- Amount: {extracted.get("amount")} {extracted.get("currency")}
- Due date: {extracted.get("due_date")}
- Items: {extracted.get("items")}

Validation results:
- Overall passed: {validation["validation_passed"]}
- Per-item verdicts: {validation["items"]}

Rule-based flags: {flags or "none"}

Prior decision: {draft["decision"]}
Prior reasoning: {draft["reasoning"]}

Critically review this decision against the facts above. If it is correct and
well-justified, confirm it with the same decision. If you find an error, an
inconsistency, or a consideration the prior reasoning missed, revise the
decision and explain specifically what changed and why.
"""

    completion = _client().beta.chat.completions.parse(
        model="grok-4.6",
        messages=[{"role": "user", "content": prompt}],
        response_format=ApprovalDecision,
    )
    return completion.choices[0].message.parsed.model_dump()
