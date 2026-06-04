from agent_runtime.events.emitter import emit


def schema_agent(state):

    emit(state["job_id"], "schema_agent", "running", "Detecting schema patterns...", 10)

    cols = state["columns"]

    schema = {
        "numeric": [c for c in cols if "id" not in c.lower()],
        "text": [c for c in cols if "name" in c.lower()]
    }

    emit(state["job_id"], "schema_agent", "completed", "Schema classification done", 20)

    state["schema"] = schema
    state["next"] = "cluster"

    return state