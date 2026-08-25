import os
import sqlite3
import xml.etree.ElementTree as ET

import pdfplumber
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()


class ExtractedItem(BaseModel):
    name: str
    qty: int


class ExtractedInvoice(BaseModel):
    vendor: str
    amount: float
    items: list[ExtractedItem]
    due_date: str | None
    currency: str


def normalize_item_name(name: str) -> str:
    """Light cleanup shared by every ingestion path. Heavier normalization
    (OCR corruption, spacing variants) is handled in the Grok prompt for
    unstructured formats, since that's the only place those variants appear.
    """
    return name.strip()


def parse_json(data: dict) -> dict:
    """Native parser for already-clean structured JSON invoices. No LLM call -
    every sample JSON invoice shares the same schema, so this is a
    deterministic key lookup, not extraction.
    """
    vendor = data.get("vendor", {})
    vendor_name = vendor.get("name") if isinstance(vendor, dict) else vendor

    items = [
        {"name": normalize_item_name(item["item"]), "qty": item["quantity"]}
        for item in data.get("line_items", [])
    ]

    return {
        "vendor": vendor_name,
        "amount": data.get("total"),
        "items": items,
        "due_date": data.get("due_date"),
        "currency": data.get("currency"),
    }


def parse_csv(rows: list[list[str]]) -> dict:
    """Native parser for CSV invoices. Detects which of the two real shapes
    this is from the header row, then delegates - the two layouts need
    genuinely different row-walking logic, not one function trying to do both.
    """
    header = [cell.strip().lower() for cell in rows[0]]
    if header == ["field", "value"]:
        return _parse_csv_vertical(rows[1:])
    return _parse_csv_tabular(header, rows[1:])


def _parse_csv_vertical(pairs: list[list[str]]) -> dict:
    """Handles the 'field,value' layout where item/quantity/unit_price repeat
    once per line item. Walks pairs in order, starting a new item group each
    time it hits an 'item' row - this is what correctly separates repeated
    keys instead of a flat dict silently overwriting earlier occurrences.
    """
    top_level = {}
    items = []
    current_item = None

    for field, value in pairs:
        field = field.strip().lower()
        value = value.strip()
        if field == "item":
            current_item = {"name": normalize_item_name(value)}
            items.append(current_item)
        elif field == "quantity":
            current_item["qty"] = int(value)
        elif field == "unit_price":
            pass  # not part of the extracted.items schema
        else:
            top_level[field] = value

    return {
        "vendor": top_level.get("vendor"),
        "amount": float(top_level["total"]) if "total" in top_level else None,
        "items": items,
        "due_date": top_level.get("due_date"),
        "currency": top_level.get("currency"),
    }


def _parse_csv_tabular(header: list[str], rows: list[list[str]]) -> dict:
    """Handles the standard one-row-per-line-item layout. A row counts as a
    real line item only if its 'item' cell is non-empty; the trailing summary
    rows (blank item, blank invoice number) are skipped for items but their
    'Total:' row is used to read the actual invoice amount directly, which is
    more reliable than summing line totals ourselves.
    """
    col = {name: i for i, name in enumerate(header)}
    vendor = None
    due_date = None
    amount = None
    items = []

    for row in rows:
        item_name = row[col["item"]].strip()
        if item_name:
            items.append({"name": normalize_item_name(item_name), "qty": int(row[col["qty"]])})
            vendor = vendor or row[col["vendor"]].strip()
            due_date = due_date or row[col["due date"]].strip()
        elif row[col["unit price"]].strip().lower().startswith("total"):
            amount = float(row[col["line total"]])

    return {
        "vendor": vendor,
        "amount": amount,
        "items": items,
        "due_date": due_date,
        "currency": None,
    }


def parse_xml(root: ET.Element) -> dict:
    """Native parser for XML invoices. Only one real sample exists in this
    dataset, so this has less cross-checking than parse_json/parse_csv - the
    format itself is simple and well-defined, which is the main reason to
    trust it despite the thin test coverage.
    """
    header = root.find("header")
    items = [
        {
            "name": normalize_item_name(item.findtext("name")),
            "qty": int(item.findtext("quantity")),
        }
        for item in root.find("line_items").findall("item")
    ]

    return {
        "vendor": header.findtext("vendor"),
        "amount": float(root.find("totals").findtext("total")),
        "items": items,
        "due_date": header.findtext("due_date"),
        "currency": header.findtext("currency"),
    }


def get_raw_text(invoice_path: str) -> str:
    """Reads .txt directly, or pulls text out of .pdf via pdfplumber. Both
    formats end up as plain text feeding the same extract_via_grok() call.
    """
    if invoice_path.endswith(".pdf"):
        with pdfplumber.open(invoice_path) as pdf:
            return "\n".join(page.extract_text() or "" for page in pdf.pages)
    with open(invoice_path) as f:
        return f.read()


def _known_item_names() -> list[str]:
    """Canonical item names, read live from inventory.db rather than
    hardcoded in the prompt, so this can't drift out of sync with the DB.
    """
    conn = sqlite3.connect("inventory.db")
    names = [row[0] for row in conn.execute("SELECT item FROM inventory").fetchall()]
    conn.close()
    return names


def extract_via_grok(raw_text: str) -> dict:
    """Extraction for unstructured text (.txt/.pdf), and the fallback for
    structured formats that fail native parsing. Item-name normalization
    happens here, in the prompt, per the brief - not as post-processing -
    since this is the only ingestion path where OCR corruption and spacing
    variants actually show up in the real sample data.
    """
    client = OpenAI(api_key=os.environ["XAI_API_KEY"], base_url="https://api.x.ai/v1")
    known_items = ", ".join(_known_item_names())

    prompt = f"""Extract structured invoice data from the text below.

Known canonical item names in our inventory system: {known_items}.
Item names in the invoice text may be OCR-corrupted, misspelled, or inconsistently
spaced (e.g. "Widget A" or "WidgetB" with odd spacing should both map to "WidgetA").
Map every item name to its closest canonical form from the list above if it clearly
matches one; otherwise leave the name exactly as written - it may be a genuinely
unknown item, do not force a match.

Invoice text:
---
{raw_text}
---
"""

    last_error = None
    for attempt in range(2):  # one retry, per the brief
        try:
            completion = client.beta.chat.completions.parse(
                model="grok-4.6",
                messages=[{"role": "user", "content": prompt}],
                response_format=ExtractedInvoice,
            )
            return completion.choices[0].message.parsed.model_dump()
        except Exception as e:
            last_error = e
    raise last_error
