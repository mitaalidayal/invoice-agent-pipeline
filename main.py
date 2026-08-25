import argparse
import json
import pathlib
from datetime import datetime, timezone

from graph import build_graph
from state import InvoiceState


def _initial_state(invoice_path: str) -> InvoiceState:
    return InvoiceState(
        invoice_path=invoice_path,
        raw_text="",
        extracted={},
        validation={},
        approval_decision="pending",
        approval_reasoning="",
        reflection_count=0,
        payment_result=None,
        log=[],
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the invoice processing pipeline on a single invoice.")
    parser.add_argument("--invoice_path", required=True, help="Path to the invoice file to process.")
    args = parser.parse_args()

    graph = build_graph()
    final_state = graph.invoke(_initial_state(args.invoice_path))

    logs_dir = pathlib.Path("logs")
    logs_dir.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    invoice_stem = pathlib.Path(args.invoice_path).stem
    log_path = logs_dir / f"{timestamp}_{invoice_stem}.json"
    log_path.write_text(json.dumps(final_state, indent=2, default=str))

    print(f"Vendor: {final_state['extracted'].get('vendor')}")
    print(f"Decision: {final_state['approval_decision']}")
    print(f"Reasoning: {final_state['approval_reasoning']}")
    print(f"Full run log: {log_path}")


if __name__ == "__main__":
    main()
