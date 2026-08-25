import datetime

from state import InvoiceState


def _timestamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _append_log(state: InvoiceState, node: str, output: dict) -> list[dict]:
    return state["log"] + [{"node": node, "timestamp": _timestamp(), "output": output}]


def ingestion_node(state: InvoiceState) -> dict:
    """Stub. Real version routes by extension and extracts via Grok / native parsing."""
    extracted = {"vendor": None, "amount": None, "items": [], "due_date": None, "currency": None}
    return {
        "raw_text": "",
        "extracted": extracted,
        "log": _append_log(state, "ingestion", extracted),
    }


def validation_node(state: InvoiceState) -> dict:
    """Stub. Real version aggregates quantities per item and calls check_inventory()."""
    validation = {"items": [], "validation_passed": True}
    return {
        "validation": validation,
        "log": _append_log(state, "validation", validation),
    }


def approval_node(state: InvoiceState) -> dict:
    """Stub. Real version applies rules + LLM decision + one bounded reflection pass."""
    decision = "approved"
    reasoning = "stub: plumbing test, no real reasoning yet"
    return {
        "approval_decision": decision,
        "approval_reasoning": reasoning,
        "log": _append_log(state, "approval", {"decision": decision, "reasoning": reasoning}),
    }


def payment_node(state: InvoiceState) -> dict:
    """Stub. Real version calls mock_payment(vendor, amount)."""
    result = {"status": "stub"}
    return {
        "payment_result": result,
        "log": _append_log(state, "payment", result),
    }


def reject_node(state: InvoiceState) -> dict:
    """Logs the rejection; no payment call."""
    return {
        "payment_result": None,
        "log": _append_log(state, "reject", {"reasoning": state["approval_reasoning"]}),
    }


def route_after_approval(state: InvoiceState) -> str:
    return "approved" if state["approval_decision"] == "approved" else "rejected"
