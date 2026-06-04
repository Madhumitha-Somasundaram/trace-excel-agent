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
from agent_runtime.nodes.targeted_transformation_engine import (
    targeted_transformation_executor_node,
    wait_for_targeted_transformation_node,
    generate_updated_template_files_node
)
from agent_runtime.nodes.transformation_router import transformation_router_node
from agent_runtime.nodes.finalize_node import finalize_node


def route(state):
    """Route to next node based on state."""
    return state.get("next", "END")


# Create graph with typed state
graph = StateGraph(AgentState)

# Add all nodes
graph.add_node("loader", loader_node)
graph.add_node("schema_detection", schema_node)
graph.add_node("cluster", cluster_node)
graph.add_node("dynamic_template_detection", dynamic_template_detection_node)
graph.add_node("generate_template_files", generate_template_files_node)
graph.add_node("transformation_router", transformation_router_node)
graph.add_node("dynamic_transformation", dynamic_transformation_executor_node)
graph.add_node("wait_for_transformation", wait_for_transformation_node)
graph.add_node("targeted_transformation", targeted_transformation_executor_node)
graph.add_node("wait_for_targeted_transformation", wait_for_targeted_transformation_node)
graph.add_node("generate_updated_template_files", generate_updated_template_files_node)
graph.add_node("finalize", finalize_node)

# Set entry point
graph.set_entry_point("loader")

# Add conditional edges (routing based on state["next"])
for node_name in [
    "loader",
    "schema_detection",
    "cluster",
    "dynamic_template_detection",
    "generate_template_files",
    "transformation_router",
    "dynamic_transformation",
    "wait_for_transformation",
    "targeted_transformation",
    "wait_for_targeted_transformation",
    "generate_updated_template_files",
    "finalize"
]:
    graph.add_conditional_edges(node_name, route)

# Compile the graph
app = graph.compile()

print("✅ Agent graph compiled successfully")
print(f"   Nodes: {len(graph.nodes)}")
print(f"   Entry point: loader")
print(f"   Dynamic template detection: ENABLED")
print(f"   Dynamic transformations: ENABLED")