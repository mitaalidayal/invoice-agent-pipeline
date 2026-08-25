from validation import aggregate_items, check_inventory, validate_items


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


def test_validate_items_clean_invoice_passes():
    result = validate_items([{"name": "WidgetA", "qty": 10}, {"name": "WidgetB", "qty": 5}])
    assert result["validation_passed"] is True
    assert all(item["verdict"] == "ok" for item in result["items"])


def test_validate_items_stock_mismatch():
    # README's own example: INV-1002 requests 20x GadgetX, only 5 in stock
    result = validate_items([{"name": "GadgetX", "qty": 20}])
    assert result["validation_passed"] is False
    assert result["items"][0]["verdict"] == "stock_mismatch"


def test_validate_items_unknown_item():
    result = validate_items([{"name": "SuperGizmo", "qty": 12}, {"name": "MegaSprocket", "qty": 6}])
    assert result["validation_passed"] is False
    assert all(item["verdict"] == "unknown_item" for item in result["items"])


def test_validate_items_negative_qty_is_data_integrity_issue():
    result = validate_items([{"name": "WidgetA", "qty": -5}])
    assert result["validation_passed"] is False
    assert result["items"][0]["verdict"] == "data_integrity_issue"


def test_validate_items_partial_match_not_all_or_nothing():
    # README's own example: INV-1016 mixes known WidgetA/WidgetB with unknown WidgetC
    result = validate_items([
        {"name": "WidgetA", "qty": 4}, {"name": "WidgetB", "qty": 2}, {"name": "WidgetC", "qty": 3},
    ])
    verdicts = {item["name"]: item["verdict"] for item in result["items"]}
    assert verdicts["WidgetA"] == "ok"
    assert verdicts["WidgetB"] == "ok"
    assert verdicts["WidgetC"] == "unknown_item"
    assert result["validation_passed"] is False


def test_validate_items_aggregates_before_checking_stock():
    # invoice_1013's real GadgetX case: 5+3+1=9 requested, only 5 in stock.
    # Checking each line separately would miss this - every individual line passes.
    result = validate_items([
        {"name": "GadgetX", "qty": 5}, {"name": "GadgetX", "qty": 3}, {"name": "GadgetX", "qty": 1},
    ])
    assert result["validation_passed"] is False
    assert result["items"][0]["verdict"] == "stock_mismatch"
    assert result["items"][0]["qty"] == 9
