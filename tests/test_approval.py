from agents import approval
from agents.approval import apply_rules


def test_no_flags_for_clean_invoice():
    assert apply_rules({"amount": 5000.0, "currency": "USD"}, {"validation_passed": True}) == []


def test_high_value_flag_over_10k():
    flags = apply_rules({"amount": 15225.0, "currency": "USD"}, {"validation_passed": True})
    assert "high_value" in flags


def test_no_high_value_flag_at_exactly_10k():
    flags = apply_rules({"amount": 10_000.0, "currency": "USD"}, {"validation_passed": True})
    assert "high_value" not in flags


def test_validation_failed_flag():
    flags = apply_rules({"amount": 5000.0, "currency": "USD"}, {"validation_passed": False})
    assert "validation_failed" in flags


def test_non_usd_flag_for_confirmed_foreign_currency():
    flags = apply_rules({"amount": 4125.0, "currency": "EUR"}, {"validation_passed": True})
    assert "non_usd" in flags


def test_no_non_usd_flag_when_currency_missing():
    # A missing currency (CSV's honest gap - no currency column exists) should
    # NOT be treated the same as a confirmed non-USD currency.
    flags = apply_rules({"amount": 2750.0, "currency": None}, {"validation_passed": True})
    assert "non_usd" not in flags


def test_multiple_flags_can_combine():
    flags = apply_rules({"amount": 15000.0, "currency": "USD"}, {"validation_passed": False})
    assert set(flags) == {"high_value", "validation_failed"}


def test_run_approval_stops_early_when_reflection_agrees(monkeypatch):
    monkeypatch.setattr(approval, "draft_decision", lambda e, v, f: {"decision": "approved", "reasoning": "draft"})
    calls = []
    monkeypatch.setattr(
        approval, "reflect_on_decision",
        lambda e, v, f, draft: calls.append(1) or {"decision": "approved", "reasoning": "confirmed"},
    )

    result = approval.run_approval({"amount": 100.0, "currency": "USD"}, {"validation_passed": True})

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

    result = approval.run_approval({"amount": 100.0, "currency": "USD"}, {"validation_passed": True})

    assert len(calls) == approval.MAX_REFLECTIONS
    assert result["reflection_count"] == approval.MAX_REFLECTIONS
