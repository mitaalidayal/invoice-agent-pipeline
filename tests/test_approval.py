from agents import approval
from agents.approval import _facts_block, apply_rules


def _validation(passed=True, vendor_approved=True):
    return {"validation_passed": passed, "vendor_approved": vendor_approved, "items": [], "price_notes": []}


def test_no_flags_for_clean_invoice():
    assert apply_rules({"amount": 5000.0, "currency": "USD"}, _validation()) == []


def test_high_value_flag_over_10k():
    flags = apply_rules({"amount": 15225.0, "currency": "USD"}, _validation())
    assert "high_value" in flags


def test_no_high_value_flag_at_exactly_10k():
    flags = apply_rules({"amount": 10_000.0, "currency": "USD"}, _validation())
    assert "high_value" not in flags


def test_validation_failed_flag():
    flags = apply_rules({"amount": 5000.0, "currency": "USD"}, _validation(passed=False))
    assert "validation_failed" in flags


def test_unapproved_vendor_flag():
    flags = apply_rules({"amount": 5000.0, "currency": "USD"}, _validation(vendor_approved=False))
    assert "unapproved_vendor" in flags


def test_non_usd_flag_for_confirmed_foreign_currency():
    flags = apply_rules({"amount": 4125.0, "currency": "EUR"}, _validation())
    assert "non_usd" in flags


def test_no_non_usd_flag_when_currency_missing():
    # A missing currency (CSV's honest gap - no currency column exists) should
    # NOT be treated the same as a confirmed non-USD currency.
    flags = apply_rules({"amount": 2750.0, "currency": None}, _validation())
    assert "non_usd" not in flags


def test_multiple_flags_can_combine():
    flags = apply_rules({"amount": 15000.0, "currency": "USD"}, _validation(passed=False, vendor_approved=False))
    assert set(flags) == {"high_value", "validation_failed", "unapproved_vendor"}


def test_run_approval_stops_early_when_reflection_agrees(monkeypatch):
    monkeypatch.setattr(approval, "draft_decision", lambda e, v, f: {"decision": "approved", "reasoning": "draft"})
    calls = []
    monkeypatch.setattr(
        approval, "reflect_on_decision",
        lambda e, v, f, draft: calls.append(1) or {"decision": "approved", "reasoning": "confirmed"},
    )

    result = approval.run_approval({"amount": 100.0, "currency": "USD"}, _validation())

    assert len(calls) == 1  # converged immediately, no need for a second pass
    assert result["reflection_count"] == 1


def test_run_approval_stops_at_max_reflections_when_never_converging(monkeypatch):
    # Reflection that always flips the decision can never converge - proves
    # the cap actually holds even in the worst case, not just that it usually
    # stops early (which is all the real-API integration tests can show).
    monkeypatch.setattr(approval, "draft_decision", lambda e, v, f: {"decision": "approved", "reasoning": "draft"})
    calls = []

    def always_flip(e, v, f, draft):
        calls.append(1)
        flipped = "rejected" if draft["decision"] == "approved" else "approved"
        return {"decision": flipped, "reasoning": f"flip {len(calls)}"}

    monkeypatch.setattr(approval, "reflect_on_decision", always_flip)

    result = approval.run_approval({"amount": 100.0, "currency": "USD"}, _validation())

    assert len(calls) == approval.MAX_REFLECTIONS
    assert result["reflection_count"] == approval.MAX_REFLECTIONS


def test_facts_block_never_exposes_raw_unit_price():
    # Regression test: showing unit_price in the raw items list let the LLM
    # attempt its own qty*price subtotal-vs-total math and flag legitimate
    # tax/shipping gaps as an "unexplained" defect (real bug, caught via a
    # live invoice_1010 run, not by any deterministic test - see git history).
    # Price signals must only reach the model through price_notes, which is
    # the deliberately-computed comparison, not raw multiplication ingredients.
    extracted = {
        "vendor": "Test Vendor", "amount": 1000.0, "currency": "USD", "due_date": "2026-01-01",
        "items": [{"name": "WidgetA", "qty": 4, "unit_price": 300.0}],
    }
    validation = {
        "validation_passed": True, "vendor_approved": True,
        "items": [{"name": "WidgetA", "qty": 4, "verdict": "ok", "available_qty": 15}],
        "price_notes": [
            {"name": "WidgetA", "invoice_unit_price": 300.0, "expected_unit_price": 250.0, "deviation_pct": 20.0}
        ],
    }

    block = _facts_block(extracted, validation, [])

    assert "'unit_price':" not in block  # the raw, bare key - distinct from invoice_/expected_unit_price below
    assert "invoice_unit_price" in block and "expected_unit_price" in block  # still present, but only via price_notes
    assert "'name': 'WidgetA', 'qty': 4" in block  # items line keeps name+qty
