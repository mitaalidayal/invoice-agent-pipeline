import csv
import datetime
import json
import xml.etree.ElementTree as ET

from approval import run_approval
from ingestion import extract_via_grok, get_raw_text, parse_csv, parse_json, parse_xml
from state import InvoiceState
from validation import validate_items


def _timestamp() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _append_log(state: InvoiceState, node: str, output: dict) -> list[dict]:
    return state["log"] + [{"node": node, "timestamp": _timestamp(), "output": output}]


def _parse_structured(invoice_path: str) -> dict:
    """Native parse for .json/.csv/.xml. Raises on structural failure - that
    exception is the signal ingestion_node uses to fall back to Grok.
    """
    if invoice_path.endswith(".json"):
        with open(invoice_path) as f:
            return parse_json(json.load(f))
    if invoice_path.endswith(".csv"):
        with open(invoice_path) as f:
            return parse_csv(list(csv.reader(f)))
    return parse_xml(ET.parse(invoice_path).getroot())  # .xml


def _extraction_failed(state: InvoiceState, raw_text: str, error: Exception) -> dict:
    return {
        "raw_text": raw_text,
        "extraction_failed": True,
        "extracted": {},
        "log": _append_log(state, "ingestion", {"error": str(error)}),
    }


def ingestion_node(state: InvoiceState) -> dict:
    invoice_path = state["invoice_path"]
    is_structured = invoice_path.endswith((".json", ".csv", ".xml"))

    try:
        raw_text = get_raw_text(invoice_path)
    except Exception as error:
        return _extraction_failed(state, "", error)

    try:
        extracted = _parse_structured(invoice_path) if is_structured else extract_via_grok(raw_text)
    except Exception as error:
        if not is_structured:
            return _extraction_failed(state, raw_text, error)
        try:
            extracted = extract_via_grok(raw_text)  # native parse failed - fall back to Grok
        except Exception as fallback_error:
            return _extraction_failed(state, raw_text, fallback_error)

    return {
        "raw_text": raw_text,
        "extraction_failed": False,
        "extracted": extracted,
        "log": _append_log(state, "ingestion", extracted),
    }


def validation_node(state: InvoiceState) -> dict:
    validation = validate_items(state["extracted"]["items"])
    return {
        "validation": validation,
        "log": _append_log(state, "validation", validation),
    }


def approval_node(state: InvoiceState) -> dict:
    result = run_approval(state["extracted"], state["validation"])
    return {
        "approval_decision": result["decision"],
        "approval_reasoning": result["reasoning"],
        "reflection_count": result["reflection_count"],
        "log": _append_log(state, "approval", result),
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


def route_after_ingestion(state: InvoiceState) -> str:
    return "failed" if state["extraction_failed"] else "ok"
