from graph import build_graph
from main import _initial_state


def test_extraction_failed_routes_to_end_without_running_other_nodes():
    graph = build_graph()
    result = graph.invoke(_initial_state("data/invoices/does_not_exist.txt"))
    assert result["extraction_failed"] is True
    ran_nodes = [entry["node"] for entry in result["log"]]
    assert ran_nodes == ["ingestion"]
    assert result["approval_decision"] == "pending"  # never reached


def test_approved_decision_routes_to_payment_not_reject(monkeypatch):
    monkeypatch.setattr(
        "nodes.run_approval",
        lambda extracted, validation: {"decision": "approved", "reasoning": "test", "reflection_count": 1, "flags": []},
    )
    graph = build_graph()
    result = graph.invoke(_initial_state("data/invoices/invoice_1005.json"))  # native parse, no Grok call
    ran_nodes = [entry["node"] for entry in result["log"]]
    assert "payment" in ran_nodes
    assert "reject" not in ran_nodes
    assert result["payment_result"] == {"status": "success"}


def test_rejected_decision_routes_to_reject_not_payment(monkeypatch):
    monkeypatch.setattr(
        "nodes.run_approval",
        lambda extracted, validation: {"decision": "rejected", "reasoning": "test", "reflection_count": 1, "flags": []},
    )
    graph = build_graph()
    result = graph.invoke(_initial_state("data/invoices/invoice_1005.json"))
    ran_nodes = [entry["node"] for entry in result["log"]]
    assert "reject" in ran_nodes
    assert "payment" not in ran_nodes
    assert result["payment_result"] is None
