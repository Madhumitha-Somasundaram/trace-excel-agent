"""
Transformation Router - Decides whether to use targeted or full transformation.

This node analyzes the user request and determines:
1. Is this a modification to existing templates? → Use targeted transformation
2. Is this a new transformation on original data? → Use full transformation
"""

import os
import boto3
from typing import Dict, Any
from tools.llm import llm_call

ddb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
jobs_table = ddb.Table("jobs")


def analyze_transformation_type(
    user_request: str,
    has_existing_templates: bool,
    has_transformed_data: bool
) -> Dict[str, Any]:
    """
    Determine if this is a targeted template update or a full transformation.

    Args:
        user_request: User's transformation request
        has_existing_templates: Whether template files already exist
        has_transformed_data: Whether data has been transformed before

    Returns:
        Dict with transformation type and routing decision
    """

    prompt = f"""Analyze this user request to determine transformation scope.

**User Request:**
"{user_request}"

**Context:**
- Existing templates available: {has_existing_templates}
- Previous transformation exists: {has_transformed_data}

**Your Task:**
Determine if this is:
1. **TARGETED**: Modifying existing templates (e.g., "convert distance to km in transportation template")
2. **FULL**: New transformation on original data (e.g., "filter all rows where amount > 1000")

Consider:
- Does the request mention "update", "modify", "change" specific templates/columns?
- Does it reference existing templates or specific columns?
- Is it asking for a new analysis/transformation from scratch?
- Is it asking to apply changes to already-generated templates?

Return JSON:
{{
  "transformation_type": "TARGETED|FULL",
  "confidence": 0.0-1.0,
  "reasoning": "why this classification",
  "applies_to_existing_templates": true/false,
  "creates_new_output": true/false,
  "keywords_detected": ["list", "of", "key", "words"],
  "recommended_approach": "targeted_transformation|full_transformation"
}}"""

    return llm_call(prompt, max_tokens=1024, temperature=0.2)


def transformation_router_node(state):
    """
    Route to appropriate transformation engine based on request type.

    Routes to:
    - "targeted_transformation" if modifying existing templates
    - "dynamic_transformation" if creating new transformation from scratch
    - "finalize" if no transformation needed
    """

    job_id = state["job_id"]
    user_request = state.get("user_request", "")

    if not user_request:
        print("[TransformationRouter] No user request - skipping transformation")
        state["next"] = "finalize"
        return state

    print(f"[TransformationRouter] Analyzing request: {user_request}")

    # Check context
    has_existing_templates = len(state.get("templates", [])) > 0
    has_transformed_data = state.get("transformed_path") is not None

    print(f"[TransformationRouter] Context: templates={has_existing_templates}, transformed={has_transformed_data}")

    # Analyze transformation type
    analysis = analyze_transformation_type(
        user_request,
        has_existing_templates,
        has_transformed_data
    )

    # Handle wrapped response from llm_call
    if "response" in analysis and isinstance(analysis["response"], dict):
        analysis = analysis["response"]

    transformation_type = analysis.get("transformation_type", "FULL")
    confidence = analysis.get("confidence", 0.0)
    reasoning = analysis.get("reasoning", "")

    print(f"[TransformationRouter] Type: {transformation_type} (confidence: {confidence:.2f})")
    print(f"[TransformationRouter] Reasoning: {reasoning}")

    # Store analysis in state
    state["transformation_routing_analysis"] = analysis

    # Route based on type
    if transformation_type == "TARGETED" and has_existing_templates:
        print("[TransformationRouter] → Routing to TARGETED transformation")
        state["next"] = "targeted_transformation"

    elif transformation_type == "FULL" or not has_existing_templates:
        print("[TransformationRouter] → Routing to FULL transformation")
        state["next"] = "dynamic_transformation"

    else:
        # Default: if unclear and templates exist, use targeted
        if has_existing_templates:
            print("[TransformationRouter] → Default to TARGETED (templates exist)")
            state["next"] = "targeted_transformation"
        else:
            print("[TransformationRouter] → Default to FULL (no templates)")
            state["next"] = "dynamic_transformation"

    jobs_table.update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET current_step = :c",
        ExpressionAttributeValues={
            ":c": f"routing_transformation: {transformation_type.lower()}"
        }
    )

    return state
