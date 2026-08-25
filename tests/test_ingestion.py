import csv
import json
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock

import pytest

from agents.ingestion import extract_via_grok, get_raw_text, normalize_item_name, parse_csv, parse_json, parse_xml


def _load_json(name):
    with open(f"data/invoices/{name}") as f:
        return json.load(f)


def _load_csv_rows(name):
    with open(f"data/invoices/{name}") as f:
        return list(csv.reader(f))


def test_normalize_item_name_strips_whitespace():
    assert normalize_item_name("  WidgetA  ") == "WidgetA"


@pytest.mark.parametrize(
    "name,expected_vendor,expected_amount,expected_item_count",
    [
        ("invoice_1004.json", "Precision Parts Ltd.", 1890.0, 2),
        ("invoice_1005.json", "Global Supply Chain Partners", 15225.0, 3),
        ("invoice_1009.json", "", -250.0, 2),  # data integrity case: empty vendor, negative total
        ("invoice_1016.json", "Widgets Inc.", 3233.0, 3),
    ],
)
def test_parse_json_real_samples(name, expected_vendor, expected_amount, expected_item_count):
    result = parse_json(_load_json(name))
    assert result["vendor"] == expected_vendor
    assert result["amount"] == expected_amount
    assert len(result["items"]) == expected_item_count


def test_parse_json_negative_qty_preserved_faithfully():
    # Ingestion extracts faithfully - it doesn't judge or fix bad data, that's Validation's job.
    result = parse_json(_load_json("invoice_1009.json"))
    widget_a = next(item for item in result["items"] if item["name"] == "WidgetA")
    assert widget_a["qty"] == -5


def test_parse_csv_vertical_layout_keeps_both_repeated_items():
    # invoice_1006 has item/quantity/unit_price each appearing twice - a naive
    # flat dict would silently drop the first occurrence.
    result = parse_csv(_load_csv_rows("invoice_1006.csv"))
    names = [item["name"] for item in result["items"]]
    assert names == ["WidgetA", "WidgetB"]
    assert result["items"][0]["qty"] == 5
    assert result["items"][1]["qty"] == 3


def test_parse_csv_tabular_amount_comes_from_total_row_not_line_sum():
    # invoice_1007's line totals sum to 14750, but the real amount (with tax)
    # is 15525, only present in the trailing "Total:" summary row.
    result = parse_csv(_load_csv_rows("invoice_1007.csv"))
    assert result["amount"] == 15525.0
    assert len(result["items"]) == 3  # summary rows must not be counted as line items


def test_parse_xml_real_sample():
    root = ET.parse("data/invoices/invoice_1014.xml").getroot()
    result = parse_xml(root)
    assert result["vendor"] == "TechParts International"
    assert result["currency"] == "EUR"
    assert result["amount"] == 4125.0


def test_get_raw_text_reads_txt_directly():
    text = get_raw_text("data/invoices/invoice_1001.txt")
    assert "Widgets Inc." in text


def test_get_raw_text_extracts_from_pdf():
    # No network call needed - pdfplumber reads a local file. Only ever
    # exercised manually before this, never in the automated suite.
    text = get_raw_text("data/invoices/invoice_1011.pdf")
    assert "Summit Manufacturing" in text


def _fake_completion(parsed_dict):
    completion = MagicMock()
    message = MagicMock()
    message.parsed.model_dump.return_value = parsed_dict
    completion.choices = [MagicMock(message=message)]
    return completion


def test_extract_via_grok_retries_once_on_failure(monkeypatch):
    success = _fake_completion(
        {"vendor": "Test Vendor", "amount": 100.0, "items": [], "due_date": None, "currency": "USD"}
    )
    client = MagicMock()
    client.beta.chat.completions.parse.side_effect = [Exception("simulated failure"), success]
    monkeypatch.setattr("agents.ingestion.OpenAI", lambda **kwargs: client)

    result = extract_via_grok("some invoice text")

    assert result["vendor"] == "Test Vendor"
    assert client.beta.chat.completions.parse.call_count == 2


def test_extract_via_grok_raises_after_exhausting_retries(monkeypatch):
    client = MagicMock()
    client.beta.chat.completions.parse.side_effect = [Exception("failure 1"), Exception("failure 2")]
    monkeypatch.setattr("agents.ingestion.OpenAI", lambda **kwargs: client)

    with pytest.raises(Exception, match="failure 2"):
        extract_via_grok("some invoice text")

    assert client.beta.chat.completions.parse.call_count == 2
