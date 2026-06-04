"""
Agent Graph with Human-in-the-Loop (HITL) Integration.

Flow with HITL:
1. Upload → Loader (Glue) → Schema → Cluster → Template Detection → Finalize
2. User requests transformation via chat
3. System generates preview → **HUMAN APPROVAL GATE** ← BLOCKS HERE
4. If approved → Execute transformation → Finalize
5. If rejected → Skip to Finalize

NO transformations execute without explicit user approval.
"""

from langgraph.graph import StateGraph
from agent_runtime.state import AgentState

# Import node functions
from agent_runtime.nodes.loader_node import loader_node
from agent_runtime.nodes.schema_node import schema_node
from agent_runtime.nodes.cluster_node import cluster_node
from agent_runtime.nodes.dynamic_template_detector import (
    dynamic_template_detection_node,
    generate_template_files_node
)
from agent_runtime.nodes.dynamic_transformation_engine import (
    dynamic_transformation_executor_node,
    wait_for_transformation_node
)
from agent_runtime.nodes.human_in_the_loop import (
    human_approval_gate_node
)
from agent_runtime.nodes.finalize_node import finalize_node


def route(state):
    """Route to next node based on state."""
    return state.get("next", "END")


# Create graph with typed state
graph = StateGraph(AgentState)

# ========== PHASE 1: INITIAL PROCESSING (No approval needed) ==========
graph.add_node("loader", loader_node)
graph.add_node("schema", schema_node)
graph.add_node("cluster", cluster_node)
graph.add_node("dynamic_template_detection", dynamic_template_detection_node)
graph.add_node("generate_template_files", generate_template_files_node)
graph.add_node("finalize", finalize_node)

# ========== PHASE 2: USER-REQUESTED TRANSFORMATIONS (Requires approval) ==========
graph.add_node("prepare_transformation", dynamic_transformation_executor_node)
graph.add_node("human_approval_gate", human_approval_gate_node)  # ← GATE NODE
graph.add_node("execute_transformation", wait_for_transformation_node)

# Set entry point
graph.set_entry_point("loader")

# Add conditional edges for initial processing
for node_name in [
    "loader",
    "schema",
    "cluster",
    "dynamic_template_detection",
    "generate_template_files",
    "finalize"
]:
    graph.add_conditional_edges(node_name, route)

# Add transformation flow with approval gate
graph.add_conditional_edges("prepare_transformation", route)
graph.add_conditional_edges("human_approval_gate", route)  # Routes based on approval decision
graph.add_conditional_edges("execute_transformation", route)

# Compile the graph
app = graph.compile()

print("✅ Agent graph with HITL compiled successfully")
print(f"   Nodes: {len(graph.nodes)}")
print(f"   Entry point: loader")
print(f"   🛡️  Human approval gate: ACTIVE")
print(f"   ⚠️  NO transformations execute without user approval")
print(f"")
print("   Transformation Flow:")
print("   1. prepare_transformation (analyze & generate code)")
print("   2. human_approval_gate (🚦 BLOCKS until user approves)")
print("   3. execute_transformation (only if approved)")
print("   4. finalize")
