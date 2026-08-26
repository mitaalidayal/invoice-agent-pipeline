"""Tests that make real calls to the Grok API. Slower and costs a small
amount, but they're the only way to actually prove the LLM behavior works,
not just that our code around it is wired correctly. Run everything with
`pytest`, or skip these for a fast/free run with `pytest -m "not integration"`.
"""

import pytest

from agents.approval import reflect_on_decision, run_approval
from agents.ingestion import get_raw_text, extract_via_grok
from agents.validation import validate_items

pytestmark = pytest.mark.integration


def test_extraction_on_clean_invoice():
    text = get_raw_text("data/invoices/invoice_1001.txt")
    result = extract_via_grok(text)
    assert result["vendor"] == "Widgets Inc."
    assert result["amount"] == 5000.0
    assert {item["name"] for item in result["items"]} == {"WidgetA", "WidgetB"}


def test_extraction_normalizes_ocr_corrupted_item_names():
    # invoice_1012 has "Widget A" (extra space) and "Gadget X" (extra space) -
    # both should map to their canonical inventory.db names.
    text = get_raw_text("data/invoices/invoice_1012.txt")
    result = extract_via_grok(text)
    names = {item["name"] for item in result["items"]}
    assert "WidgetA" in names
    assert "GadgetX" in names


def test_extraction_does_not_force_match_genuinely_unknown_items():
    # invoice_1008 has SuperGizmo/MegaSprocket, which aren't in inventory.db -
    # extraction should leave them as-is, not force them onto a known name.
    text = get_raw_text("data/invoices/invoice_1008.txt")
    result = extract_via_grok(text)
    names = {item["name"] for item in result["items"]}
    assert "SuperGizmo" in names
    assert "MegaSprocket" in names


def test_reflection_catches_and_corrects_a_bad_draft():
    # invoice_1002's real facts clearly call for rejection (GadgetX stock
    # mismatch). Feed reflect_on_decision a deliberately wrong "approved"
    # draft and confirm it actually catches and flips it, proving the
    # self-correction loop has real teeth rather than rubber-stamping.
    extracted = {
        "vendor": "Gadgets Co.", "amount": 15000.0, "currency": "USD",
        "items": [{"name": "GadgetX", "qty": 20, "unit_price": 750.0}], "due_date": "2026-01-30",
    }
    validation = validate_items(extracted["vendor"], extracted["items"])
    bad_draft = {"decision": "approved", "reasoning": "Looks fine, approving."}

    fixed = reflect_on_decision(extracted, validation, ["high_value", "validation_failed"], bad_draft)

    assert fixed["decision"] == "rejected"


def test_legitimate_price_deviation_does_not_cause_rejection():
    # Real bug this locks in: invoice_1010's genuine $2000 tax+shipping (not
    # captured as separate fields) was misread by the LLM as an "unexplained
    # gap" once unit_price was visible in the raw items list, flipping this
    # otherwise-clean invoice from approved to rejected. Fixed by keeping
    # unit_price out of the raw items display; this test replicates the
    # exact real scenario end-to-end to make sure it stays fixed.
    text = get_raw_text("data/invoices/invoice_1010.txt")
    extracted = extract_via_grok(text)
    validation = validate_items(extracted["vendor"], extracted["items"])

    result = run_approval(extracted, validation)

    assert result["decision"] == "approved"
