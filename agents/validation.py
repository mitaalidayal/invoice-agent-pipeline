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


def validate_items(items: list[dict]) -> dict:
    """Aggregates first, then assigns one verdict per (already-aggregated)
    item: negative qty is checked before the DB lookup, since it's a data
    problem regardless of whether the item exists or how much stock there is.
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

    return {
        "items": results,
        "validation_passed": all(r["verdict"] == "ok" for r in results),
    }
