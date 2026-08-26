from langgraph.graph import END, StateGraph

from nodes import (
    approval_node,
    hold_for_review_node,
    ingestion_node,
    payment_node,
    reject_node,
    route_after_approval,
    route_after_ingestion,
    validation_node,
)
from state import InvoiceState


def build_graph():
    builder = StateGraph(InvoiceState)
    builder.add_node("ingestion", ingestion_node)
    builder.add_node("validation", validation_node)
    builder.add_node("approval", approval_node)
    builder.add_node("payment", payment_node)
    builder.add_node("reject", reject_node)
    builder.add_node("hold_for_review", hold_for_review_node)

    builder.set_entry_point("ingestion")
    builder.add_conditional_edges(
        "ingestion",
        route_after_ingestion,
        {"ok": "validation", "failed": END},
    )
    builder.add_edge("validation", "approval")
    builder.add_conditional_edges(
        "approval",
        route_after_approval,
        {"approved": "payment", "rejected": "reject", "pending_review": "hold_for_review"},
    )
    builder.add_edge("payment", END)
    builder.add_edge("reject", END)
    builder.add_edge("hold_for_review", END)

    return builder.compile()
