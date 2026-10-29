"""Debug script for A10 graph execution."""
import json
from ai_workflow_hub.workflows.paper_graph import (
    compile_paper_graph, diagnosis_node, acceptance_gate_node,
    paper_finalizer_node, _route_after_acceptance,
)

# Test diagnosis node directly
state = {
    'writelab_mode': 'mock',
    'all_review_issues': [],
    'expression_issues': [],
    'paragraph_issues': [],
    'executed_nodes': [],
    'acceptance_result': {},
    'acceptance_status': '',
    'blocking_count': 0,
    'non_blocking_count': 0,
    'privacy_attestation': {},
    'status': 'pending',
}

# Run diagnosis
d_result = diagnosis_node(state)
print("=== diagnosis_node result ===")
for k, v in d_result.items():
    print(f"  {k}: {v!r}")

# Merge into state
state.update(d_result)

# Run acceptance gate
ag_result = acceptance_gate_node(state)
print("\n=== acceptance_gate_node result ===")
for k, v in ag_result.items():
    print(f"  {k}: {v!r}")

# Merge
state.update(ag_result)
print(f"\nacceptance_status: {state.get('acceptance_status')}")
ar = state.get('acceptance_result', {})
print(f"acceptance_result: {json.dumps(ar, indent=2, default=str)}")

# Route
route = _route_after_acceptance(state)
print(f"\nroute: {route}")

# Finalizer
if route == "finalizer":
    f_result = paper_finalizer_node(state)
    print(f"\n=== paper_finalizer_node result ===")
    for k, v in f_result.items():
        print(f"  {k}: {v!r}")

# Now test with full graph invoke
print("\n\n=== Full graph invoke ===")
compiled = compile_paper_graph("debug-1")
config = {"configurable": {"thread_id": "debug-1"}}
result = compiled.invoke({
    "writelab_mode": "mock",
    "all_review_issues": [],
}, config)

print(f"Final status: {result['status']}")
print(f"Acceptance status: {result.get('acceptance_status', 'N/A')}")
print(f"Executed nodes: {result.get('executed_nodes', [])}")
print(f"Blocking count: {result.get('blocking_count', 0)}")
ar = result.get('acceptance_result', {})
print(f"Acceptance result status: {ar.get('status', 'N/A')}")
print(f"Acceptance result reasons: {ar.get('reasons', [])}")
