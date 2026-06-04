"""
Finalize Node - Completes the agent pipeline and prepares results.
"""

import os
import boto3
import json
from tools.s3_tool import s3, BUCKET

ddb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
jobs_table = ddb.Table("jobs")




def finalize_node(state):
    """
    Finalize the processing pipeline and save results.
    """
    job_id = state["job_id"]

    print(f"[FinalizeNode] Finalizing job {job_id}")

    raw_templates = state.get("templates", {})
    templates_list = []

    if isinstance(raw_templates, dict):
        templates_list = list(raw_templates.values())

    elif isinstance(raw_templates, list):
        templates_list = [
        t for t in raw_templates
        if isinstance(t, dict)
    ]
    results = {
        "job_id": job_id,
        "status": "COMPLETED",
        "profile": state.get("raw_profile", {}),
        "schema": state.get("schema", {}),
        "clusters": state.get("clusters", {}),
        "templates": templates_list,
        "template_count": len(templates_list),
        "cleaned_data_path": state.get("cleaned_path", ""),
        "transformed_path": state.get("transformed_path", ""),
        "next_steps": [
            "Download templates",
            "Request transformations",
            "Ask analytical questions"
        ],
    }

    # Include clarification data if present
    if state.get("clarification_needed"):
        results["clarification_needed"] = True
        results["clarification_message"] = state.get("clarification_message", "")
        results["clarification_questions"] = state.get("clarification_questions", [])

    print("[FinalizeNode] Generating template download links...")
    template_files = state.get("template_files", [])
    results["template_downloads"] = template_files
    user_id = state["s3_key"].split("/")[0]
    results_key = f"{user_id}/{job_id}/results.json"

    s3.put_object(
        Bucket=BUCKET,
        Key=results_key,
        Body=json.dumps(results, indent=2),
        ContentType="application/json",
    )

    # Update DynamoDB with clarification status if needed
    update_expr = "SET #s = :s, current_step = :c, progress = :p, results_key = :r"
    expr_values = {
        ":s": "COMPLETED",
        ":c": "processing_complete",
        ":p": 100,
        ":r": results_key,
    }
    expr_names = {"#s": "status"}

    if state.get("clarification_needed"):
        update_expr += ", clarification_needed = :cn, clarification_message = :cm"
        expr_values[":cn"] = True
        expr_values[":cm"] = state.get("clarification_message", "")

    jobs_table.update_item(
        Key={"job_id": job_id},
        UpdateExpression=update_expr,
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
    )

    state["results"] = results
    state["next"] = "END"

    print(f"[FinalizeNode] Job {job_id} completed successfully")
    return state