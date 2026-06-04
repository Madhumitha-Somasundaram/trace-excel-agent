from tools.llm import llm_call


def reasoning_node(state):

    prompt = f"""
You are a data science AI agent.

You have processed dataset in AWS Glue.

Current state:
{state}

Decide next step:
- profile_more
- clean_more
- schema_detect
- cluster_columns
- generate_templates
- finish

Return JSON:
{{
  "next": "",
  "reason": ""
}}
"""

    decision = llm_call(prompt)

    state["next"] = decision["next"]

    return state