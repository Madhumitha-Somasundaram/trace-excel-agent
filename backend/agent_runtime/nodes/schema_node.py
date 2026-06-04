"""
Schema detection node wrapper for graph compatibility
"""
from agent_runtime.events.emitter import emit


def schema_node(state):
    """Detect schema patterns in the data"""

    emit(state["job_id"], "schema_node", "running", "Detecting schema patterns...", 10)

    cols = state.get("columns", [])

    schema = {
        "numeric": [c for c in cols if "id" not in c.lower()],
        "text": [c for c in cols if "name" in c.lower()]
    }

    emit(state["job_id"], "schema_node", "completed", "Schema classification done", 20)

    state["schema"] = schema
    state["next"] = "cluster"

    return state
