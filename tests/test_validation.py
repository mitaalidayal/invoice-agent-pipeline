from agents.validation import aggregate_items, check_inventory, check_price, check_vendor, validate_items

APPROVED_VENDOR = "Widgets Inc."


def test_aggregate_items_sums_repeated_names():
    items = [
        {"name": "WidgetA", "qty": 15}, {"name": "WidgetB", "qty": 10}, {"name": "GadgetX", "qty": 5},
        {"name": "WidgetA", "qty": 5}, {"name": "WidgetB", "qty": 8}, {"name": "GadgetX", "qty": 3},
        {"name": "WidgetA", "qty": 2}, {"name": "GadgetX", "qty": 1},
    ]
    assert aggregate_items(items) == {"WidgetA": 22, "WidgetB": 18, "GadgetX": 9}


def test_check_inventory_found_and_in_stock():
    assert check_inventory("WidgetA", 12) == {"found": True, "in_stock": True, "available_qty": 15}


def test_check_inventory_found_but_exceeds_stock():
    assert check_inventory("GadgetX", 9) == {"found": True, "in_stock": False, "available_qty": 5}


def test_check_inventory_not_found():
    assert check_inventory("SuperGizmo", 1) == {"found": False, "in_stock": False, "available_qty": None}


def test_check_price_matches_canonical():
    result = check_price("WidgetA", 250.0)
    assert result == {"found": True, "expected_price": 250.0, "deviation_pct": 0.0}


def test_check_price_flags_deviation():
    # invoice_1010's real "rush order" surcharge: $300 vs canonical $250
    result = check_price("WidgetA", 300.0)
    assert result["found"] is True
    assert result["expected_price"] == 250.0
    assert result["deviation_pct"] == 20.0


def test_check_price_unknown_item():
    assert check_price("SuperGizmo", 100.0) == {"found": False, "expected_price": None, "deviation_pct": None}


def test_check_vendor_approved():
    assert check_vendor("Widgets Inc.") == {"approved": True}


def test_check_vendor_not_approved():
    # invoice_1003's real fraud-pattern vendor - deliberately excluded from
    # approved_vendors, same pattern as inventory.db excluding unknown items.
    assert check_vendor("Fraudster LLC") == {"approved": False}


def test_validate_items_clean_invoice_passes():
    result = validate_items(APPROVED_VENDOR, [
        {"name": "WidgetA", "qty": 10, "unit_price": 250.0},
        {"name": "WidgetB", "qty": 5, "unit_price": 500.0},
    ])
    assert result["validation_passed"] is True
    assert all(item["verdict"] == "ok" for item in result["items"])
    assert result["vendor_approved"] is True
    assert result["price_notes"] == []


def test_validate_items_stock_mismatch():
    # README's own example: INV-1002 requests 20x GadgetX, only 5 in stock
    result = validate_items(APPROVED_VENDOR, [{"name": "GadgetX", "qty": 20, "unit_price": 750.0}])
    assert result["validation_passed"] is False
    assert result["items"][0]["verdict"] == "stock_mismatch"


def test_validate_items_unknown_item():
    result = validate_items(APPROVED_VENDOR, [
        {"name": "SuperGizmo", "qty": 12, "unit_price": 100.0},
        {"name": "MegaSprocket", "qty": 6, "unit_price": 100.0},
    ])
    assert result["validation_passed"] is False
    assert all(item["verdict"] == "unknown_item" for item in result["items"])


def test_validate_items_negative_qty_is_data_integrity_issue():
    result = validate_items(APPROVED_VENDOR, [{"name": "WidgetA", "qty": -5, "unit_price": 250.0}])
    assert result["validation_passed"] is False
    assert result["items"][0]["verdict"] == "data_integrity_issue"


def test_validate_items_partial_match_not_all_or_nothing():
    # README's own example: INV-1016 mixes known WidgetA/WidgetB with unknown WidgetC
    result = validate_items(APPROVED_VENDOR, [
        {"name": "WidgetA", "qty": 4, "unit_price": 250.0},
        {"name": "WidgetB", "qty": 2, "unit_price": 500.0},
        {"name": "WidgetC", "qty": 3, "unit_price": 350.0},
    ])
    verdicts = {item["name"]: item["verdict"] for item in result["items"]}
    assert verdicts["WidgetA"] == "ok"
    assert verdicts["WidgetB"] == "ok"
    assert verdicts["WidgetC"] == "unknown_item"
    assert result["validation_passed"] is False


def test_validate_items_aggregates_before_checking_stock():
    # invoice_1013's real GadgetX case: 5+3+1=9 requested, only 5 in stock.
    # Checking each line separately would miss this - every individual line passes.
    result = validate_items(APPROVED_VENDOR, [
        {"name": "GadgetX", "qty": 5, "unit_price": 750.0},
        {"name": "GadgetX", "qty": 3, "unit_price": 750.0},
        {"name": "GadgetX", "qty": 1, "unit_price": 750.0},
    ])
    assert result["validation_passed"] is False
    assert result["items"][0]["verdict"] == "stock_mismatch"
    assert result["items"][0]["qty"] == 9


def test_validate_items_price_deviation_does_not_fail_validation():
    # invoice_1010's real case: WidgetA at $300 (rush order) is a legitimate
    # deviation, not an error - must not flip validation_passed to False.
    result = validate_items(APPROVED_VENDOR, [{"name": "WidgetA", "qty": 4, "unit_price": 300.0}])
    assert result["validation_passed"] is True
    assert result["price_notes"] == [
        {"name": "WidgetA", "invoice_unit_price": 300.0, "expected_unit_price": 250.0, "deviation_pct": 20.0}
    ]


def test_validate_items_unapproved_vendor_fails_validation():
    result = validate_items("Fraudster LLC", [{"name": "WidgetA", "qty": 1, "unit_price": 250.0}])
    assert result["validation_passed"] is False
    assert result["vendor_approved"] is False
