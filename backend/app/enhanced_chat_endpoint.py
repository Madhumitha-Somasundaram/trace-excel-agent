"""
Enhanced Chat Endpoint - Preview transformations before executing.

Shows users exactly what will happen with their data before running it.
"""

from fastapi import HTTPException
import boto3
import json
from tools.llm import llm_call
from agent_runtime.nodes.dynamic_transformation_engine import (
    analyze_user_intent,
    generate_pyspark_code_from_analysis
)

s3_client = boto3.client('s3')
ddb = boto3.resource('dynamodb')
table = ddb.Table('jobs')
BUCKET = "excel-trace-agent-bucket"


async def enhanced_chat(message_data: dict):
    """
    Enhanced chat that previews transformations.

    Flow:
    1. Parse user request
    2. Analyze intent
    3. Generate transformation preview
    4. Show user what will happen
    5. Ask for confirmation
    """

    job_id = message_data['job_id']
    user_message = message_data['message']

    # Load job context
    response = table.get_item(Key={"job_id": job_id})

    if 'Item' not in response:
        raise HTTPException(status_code=404, detail="Job not found")

    job = response['Item']

    if job['status'] != 'COMPLETED':
        return {
            "type": "status_message",
            "message": f"Job is still processing (status: {job['status']}). Please wait.",
            "status": job['status'],
            "progress": job.get('progress', 0)
        }

    # Load full job context (schema, samples, templates)
    user_id = job['user_id']

    # Load columns
    columns_key = f"{user_id}/{job_id}/processed/columns.json"
    columns_obj = s3_client.get_object(Bucket=BUCKET, Key=columns_key)
    columns_data = json.loads(columns_obj['Body'].read())
    columns = columns_data['columns']

    # Load sample data
    sample_key = f"{user_id}/{job_id}/processed/sample.json"
    sample_obj = s3_client.get_object(Bucket=BUCKET, Key=sample_key)
    sample_data = json.loads(sample_obj['Body'].read())

    # Load profile
    profile_key = f"{user_id}/{job_id}/processed/profile.json"
    profile_obj = s3_client.get_object(Bucket=BUCKET, Key=profile_key)
    profile = json.loads(profile_obj['Body'].read())

    # Load templates
    templates_key = f"{user_id}/{job_id}/templates/metadata.json"
    try:
        templates_obj = s3_client.get_object(Bucket=BUCKET, Key=templates_key)
        templates_meta = json.loads(templates_obj['Body'].read())
        templates = templates_meta.get('templates', {})
    except:
        templates = {}

    # Determine if this is a question or transformation request
    intent_context = {
        'template_names': [t.get('template_name', '') for t in templates.values()],
        'total_columns': len(columns),
        'total_rows': profile.get('total_rows', 0),
        'sample_columns': columns[:20]
    }

    # Analyze intent
    intent_analysis = analyze_user_intent(user_message, intent_context)

    # If it's just a question (not a transformation), answer directly
    if intent_analysis.get('intent_type') not in [
        'conversion', 'aggregation', 'filtering', 'enrichment',
        'cleaning', 'reshaping', 'statistical', 'custom'
    ]:
        # Handle as informational query
        answer_prompt = f"""Answer this question about the user's dataset.

Dataset context:
- {profile.get('total_rows', 0)} rows, {len(columns)} columns
- Templates: {[t.get('template_name') for t in templates.values()]}
- Data quality: {json.dumps(profile.get('data_quality', {}))}

User question: "{user_message}"

Provide a helpful, conversational answer. Be specific and reference actual data from their file."""

        answer = llm_call(answer_prompt, max_tokens=1024)

        return {
            "type": "informational",
            "response": answer.get('response', answer.get('text', 'I can help you with that!')),
            "is_transformation": False
        }

    # It's a transformation request - generate preview
    print(f"[EnhancedChat] Transformation request detected: {intent_analysis.get('intent_type')}")

    # Check if clarification is needed
    if intent_analysis.get('needs_clarification'):
        return {
            "type": "clarification",
            "message": "I need some clarification to proceed:",
            "questions": intent_analysis.get('clarification_questions', []),
            "similar_examples": intent_analysis.get('similar_examples', []),
            "is_transformation": True
        }

    # Generate the transformation code
    code_result = generate_pyspark_code_from_analysis(
        intent_analysis,
        profile,
        sample_data,
        templates
    )

    # Create transformation preview
    explanation = code_result.get('explanation', {})

    preview = {
        "type": "transformation_preview",
        "is_transformation": True,
        "transformation": {
            "request": user_message,
            "intent": intent_analysis.get('intent_type'),
            "confidence": intent_analysis.get('confidence', 0.8),
            "what_will_happen": explanation.get('what_it_does', ''),
            "steps": explanation.get('steps', []),
            "input": {
                "columns": code_result.get('input_columns', []),
                "rows": profile.get('total_rows', 0)
            },
            "output": {
                "columns": code_result.get('output_columns', []),
                "new_columns": code_result.get('new_columns_created', []),
                "modified_columns": code_result.get('modified_columns', []),
                "expected_rows": code_result.get('validation', {}).get('expected_row_count_change', 'same')
            },
            "performance": {
                "estimated_time": code_result.get('estimated_execution_time', 'unknown'),
                "recommended_workers": code_result.get('glue_worker_recommendation', '10 G.1X'),
                "data_size": profile.get('total_rows', 0)
            },
            "edge_cases_handled": explanation.get('edge_cases_handled', [])
        },
        "preview_code": code_result.get('pyspark_code', ''),
        "action_required": "confirm",
        "confirm_message": "Does this look correct? Reply 'Yes' to execute, or ask me to modify it."
    }

    return preview


async def confirm_and_execute_transformation(job_id: str, transformation_preview: dict):
    """
    User confirmed - execute the transformation.
    """

    # Queue transformation via SQS
    sqs = boto3.client('sqs')
    QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/549955691461/excel-trace-queue"

    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps({
            "job_id": job_id,
            "action": "transform",
            "transformation_preview": transformation_preview
        })
    )

    return {
        "type": "execution_started",
        "message": "Transformation queued! This will take a few minutes.",
        "job_id": job_id,
        "estimated_time": transformation_preview.get('transformation', {}).get('performance', {}).get('estimated_time'),
        "track_progress": f"/job/{job_id}"
    }
