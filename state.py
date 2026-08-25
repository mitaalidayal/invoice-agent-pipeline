from typing import TypedDict


class InvoiceState(TypedDict):
    invoice_path: str
    raw_text: str
    extracted: dict
    extraction_failed: bool
    validation: dict
    approval_decision: str
    approval_reasoning: str
    reflection_count: int
    payment_result: dict | None
    log: list[dict]
