from langgraph.graph import END, StateGraph

from nodes import (
    approval_node,
    ingestion_node,
    payment_node,
    reject_node,
    route_after_approval,
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

    builder.set_entry_point("ingestion")
    builder.add_edge("ingestion", "validation")
    builder.add_edge("validation", "approval")
    builder.add_conditional_edges(
        "approval",
        route_after_approval,
        {"approved": "payment", "rejected": "reject"},
    )
    builder.add_edge("payment", END)
    builder.add_edge("reject", END)

    return builder.compile()
