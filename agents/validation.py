import sqlite3


def aggregate_items(items: list[dict]) -> dict[str, int]:
    """Sums qty per item name across all line items. Required because neither
    the native parsers nor Ingestion's LLM extraction reliably merge repeated
    line items for the same item (e.g. invoice_1013.json has GadgetX split
    across 3 line items) - checking stock per raw line item instead of per
    aggregated total would miss real stock mismatches.
    """
    totals: dict[str, int] = {}
    for item in items:
        totals[item["name"]] = totals.get(item["name"], 0) + item["qty"]
    return totals


def check_inventory(item_name: str, qty: int) -> dict:
    """The actual tool: one SQLite lookup against inventory.db."""
    conn = sqlite3.connect("inventory.db")
    row = conn.execute("SELECT stock FROM inventory WHERE item = ?", (item_name,)).fetchone()
    conn.close()

    if row is None:
        return {"found": False, "in_stock": False, "available_qty": None}

    available_qty = row[0]
    return {"found": True, "in_stock": qty <= available_qty, "available_qty": available_qty}


def check_price(item_name: str, unit_price: float) -> dict:
    """Tool: what's the canonical unit price for this item, and how far off
    is the invoice's stated price? found=False for unknown items - there's
    nothing to compare against, and they're already flagged separately.
    """
    conn = sqlite3.connect("inventory.db")
    row = conn.execute("SELECT unit_price FROM inventory WHERE item = ?", (item_name,)).fetchone()
    conn.close()

    if row is None:
        return {"found": False, "expected_price": None, "deviation_pct": None}

    expected = row[0]
    deviation_pct = round((unit_price - expected) / expected * 100, 1)
    return {"found": True, "expected_price": expected, "deviation_pct": deviation_pct}


def check_vendor(vendor_name: str) -> dict:
    """Tool: is this vendor on our approved list? Mirrors check_inventory's
    pattern exactly, just against approved_vendors instead of inventory.
    """
    conn = sqlite3.connect("inventory.db")
    row = conn.execute("SELECT 1 FROM approved_vendors WHERE vendor = ?", (vendor_name,)).fetchone()
    conn.close()
    return {"approved": row is not None}


def _price_deviations(items: list[dict]) -> list[dict]:
    """Per-line-item price deviations from canonical, checked on raw items
    before aggregation - a deviation (e.g. a rush-order surcharge on one
    specific line) is a property of that line, not a blended property of
    "this item in general" on the invoice. Only non-zero deviations are
    included; an exact price match isn't worth surfacing.
    """
    notes = []
    for item in items:
        price = check_price(item["name"], item["unit_price"])
        if price["found"] and price["deviation_pct"] != 0:
            notes.append({
                "name": item["name"],
                "invoice_unit_price": item["unit_price"],
                "expected_unit_price": price["expected_price"],
                "deviation_pct": price["deviation_pct"],
            })
    return notes


def validate_items(vendor: str, items: list[dict]) -> dict:
    """Aggregates first, then assigns one verdict per (already-aggregated)
    item: negative qty is checked before the DB lookup, since it's a data
    problem regardless of whether the item exists or how much stock there is.

    Price deviations are informational only (see _price_deviations) - they
    don't affect validation_passed, since legitimate variation (volume
    discounts, rush surcharges) is real in the actual sample data and a hard
    price-match rule would produce false positives on invoices that are
    otherwise correct. Vendor approval DOES affect validation_passed, same
    severity as an unknown item - it's a fraud-relevant identity check, not
    a soft signal.
    """
    results = []
    for name, qty in aggregate_items(items).items():
        if qty < 0:
            results.append({"name": name, "qty": qty, "verdict": "data_integrity_issue"})
            continue

        inventory = check_inventory(name, qty)
        if not inventory["found"]:
            verdict = "unknown_item"
        elif not inventory["in_stock"]:
            verdict = "stock_mismatch"
        else:
            verdict = "ok"
        results.append({"name": name, "qty": qty, "verdict": verdict, "available_qty": inventory["available_qty"]})

    vendor_approved = check_vendor(vendor)["approved"]

    return {
        "items": results,
        "price_notes": _price_deviations(items),
        "vendor_approved": vendor_approved,
        "validation_passed": all(r["verdict"] == "ok" for r in results) and vendor_approved,
    }
