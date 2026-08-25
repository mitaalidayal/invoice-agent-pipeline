import json

from nodes import ingestion_node
from state import InvoiceState


def _state_for(path):
    return InvoiceState(
        invoice_path=str(path), raw_text="", extracted={}, extraction_failed=False,
        validation={}, approval_decision="pending", approval_reasoning="",
        reflection_count=0, payment_result=None, log=[],
    )


def test_ingestion_node_falls_back_to_grok_when_native_json_parse_fails(tmp_path, monkeypatch):
    # A line item missing "quantity" - parse_json's list comprehension does
    # item["quantity"], which raises KeyError. This is a genuine structural
    # parse failure, not just a "weird value" like a negative quantity.
    malformed = tmp_path / "broken.json"
    malformed.write_text(json.dumps({"vendor": {"name": "Test"}, "line_items": [{"item": "WidgetA"}], "total": 100}))

    fake_result = {"vendor": "Fallback Vendor", "amount": 999.0, "items": [], "due_date": None, "currency": "USD"}
    calls = []
    monkeypatch.setattr("nodes.extract_via_grok", lambda raw_text: calls.append(raw_text) or fake_result)

    result = ingestion_node(_state_for(malformed))

    assert len(calls) == 1  # proves the fallback path actually ran, not a coincidental match
    assert result["extraction_failed"] is False
    assert result["extracted"] == fake_result


def test_ingestion_node_fails_gracefully_when_both_native_parse_and_fallback_fail(tmp_path, monkeypatch):
    malformed = tmp_path / "broken.json"
    malformed.write_text(json.dumps({"vendor": {"name": "Test"}, "line_items": [{"item": "WidgetA"}], "total": 100}))

    monkeypatch.setattr("nodes.extract_via_grok", lambda raw_text: (_ for _ in ()).throw(RuntimeError("grok down")))

    result = ingestion_node(_state_for(malformed))

    assert result["extraction_failed"] is True
    assert result["extracted"] == {}
