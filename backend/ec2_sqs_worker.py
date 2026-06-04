"""
EC2 SQS Worker for Excel Processing

This runs continuously on EC2 and polls SQS for jobs.
Much better than Lambda for:
- Large dependencies (no size limits)
- Long-running jobs (no 15min timeout)
- Heavy processing (more control over resources)
"""

import json
import boto3
import time
import sys
import os
import signal
from datetime import datetime, timezone

# Add agent runtime to path
sys.path.append(os.path.dirname(__file__))

from agent_runtime.graph import app as agent_app
from agent_runtime.state import AgentState

# Configuration
QUEUE_URL = os.environ.get("QUEUE_URL", "https://sqs.us-east-1.amazonaws.com/549955691461/excel-trace-queue")
BUCKET = os.environ.get("BUCKET_NAME", "excel-trace-agent-bucket-549955691461")
REGION = os.environ.get("AWS_REGION", "us-east-1")

# AWS clients with region
sqs = boto3.client("sqs", region_name=REGION)
ddb = boto3.resource("dynamodb", region_name=REGION)
s3 = boto3.client("s3", region_name=REGION)
jobs_table = ddb.Table("jobs")

# Graceful shutdown
shutdown_flag = False

def signal_handler(sig, frame):  # noqa: ARG001
    global shutdown_flag
    print("🛑 Shutdown signal received. Finishing current job...")
    shutdown_flag = True

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def poll_queue():
    """
    Continuously poll SQS queue for messages.
    """
    print(f"🚀 EC2 SQS Worker started")
    print(f"📍 Queue: {QUEUE_URL}")
    print(f"📦 Bucket: {BUCKET}")
    print(f"🌍 Region: {REGION}")
    print("-" * 60)

    while not shutdown_flag:
        try:
            # Poll SQS (long polling - 20 seconds)
            response = sqs.receive_message(
                QueueUrl=QUEUE_URL,
                MaxNumberOfMessages=1,  # Process one at a time
                WaitTimeSeconds=20,  # Long polling
                VisibilityTimeout=900,  # 15 minutes to process
                MessageAttributeNames=["All"],
            )

            messages = response.get("Messages", [])

            if not messages:
                print("⏳ No messages. Waiting...")
                continue

            for message in messages:
                try:
                    # Parse message
                    receipt_handle = message["ReceiptHandle"]
                    body = json.loads(message["Body"])

                    print(f"\n📨 Received message: {json.dumps(body, indent=2)}")

                    job_id = body["job_id"]
                    s3_key = body.get("s3_key")
                    action = body.get("action", "process")
                    
                    # Delete message from queue (success)
                    sqs.delete_message(
                        QueueUrl=QUEUE_URL, ReceiptHandle=receipt_handle
                    )
                    print(f"✅ Message deleted from queue")

                    # Process based on action
                    if action == "process":
                        if not s3_key:
                            raise ValueError("s3_key is required for process action")
                        print(f"🔄 Processing file for job {job_id}")
                        process_file(job_id, s3_key)

                    elif action == "transform":
                        transformation = body.get("transformation", "")
                        print(f"✨ Applying transformation for job {job_id}")
                        apply_transformation(job_id, transformation)

                    else:
                        print(f"❌ Unknown action: {action}")


                except Exception as e:
                    error_msg = f"Error processing message: {str(e)}"
                    print(f"❌ {error_msg}")

                    # Update job with error
                    if "job_id" in body:
                        jobs_table.update_item(
                            Key={"job_id": body["job_id"]},
                            UpdateExpression="SET #s = :s, error_message = :e, updated_at = :u",
                            ExpressionAttributeNames={"#s": "status"},
                            ExpressionAttributeValues={
                                ":s": "FAILED",
                                ":e": error_msg,
                                ":u": datetime.now(timezone.utc).isoformat(),
                            },
                        )

                    # Don't delete message - let it retry or go to DLQ
                    import traceback
                    traceback.print_exc()

        except Exception as e:
            print(f"⚠️  Queue polling error: {str(e)}")
            time.sleep(5)  # Back off on error

    print("👋 Worker shutdown complete")


def process_file(job_id: str, s3_key: str):
    """
    Run the main agent graph for file processing.
    """
    print(f"[process_file] Starting agent graph for {job_id}")

    # Initialize agent state
    initial_state: AgentState = {
        "job_id": job_id,
        "s3_key": s3_key,
        "step": "loader",
        "raw_profile": {},
        "cleaned_path": "",
        "schema": {},
        "clusters": {},
        "templates": {},
        "glue_script": "",
        "glue_output": "",
        "next": "loader",
    }

    # Run agent graph
    try:
        final_state = agent_app.invoke(initial_state)

        print(f"[process_file] ✅ Agent graph completed for {job_id}")
        print(f"Final state: {json.dumps(final_state, default=str, indent=2)}")
        print(final_state)
        return final_state

    except Exception as e:
        print(f"[process_file] ❌ Agent graph error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise e
def apply_transformation(job_id: str, transformation: str):
    """
    Apply user-requested transformation.
    """

    print(f"[apply_transformation] Job {job_id}: {transformation}")

    # Load existing job state from DynamoDB
    response = jobs_table.get_item(Key={"job_id": job_id})

    if "Item" not in response:
        raise Exception(f"Job {job_id} not found")

    print(response)
    job = response["Item"]

    if job["status"] != "COMPLETED":
        raise Exception(
            f"Job must be completed before applying transformations. Current status: {job['status']}"
        )

    # Load original job results
    results_key = f"{job['user_id']}/{job_id}/results.json"

    try:
        results_obj = s3.get_object(Bucket=BUCKET, Key=results_key)
        results = json.loads(results_obj["Body"].read())
    except Exception as e:
        print(f"Error loading results: {e}")
        results = {}

    # Build state for transformation
    # IMPORTANT: Ensure templates is a list, not dict
    templates = results.get("templates", [])

    if isinstance(templates, dict):
        templates = list(templates.values())

    state: AgentState = {
        "job_id": job_id,
        "s3_key": job["s3_key"],
        "user_request": transformation,
        "raw_profile": results.get("profile", {}),
        "cleaned_path": f"s3://{BUCKET}/{job['user_id']}/{job_id}/processed/cleaned_data/",
        "schema": results.get("schema", {}),
        "clusters": results.get("clusters", {}),
        "templates": templates,  # Now guaranteed list
        "template_files": results.get("template_downloads", []),  # Load from template_downloads
        "glue_script": "",
        "glue_output": "",
        "next": "transformation_router",  # Route through router first
    }

    print("ec2_sqs_worker state:", state)

    # Load columns and sample data
    try:
        columns_key = f"{job['user_id']}/{job_id}/processed/columns.json"
        columns_obj = s3.get_object(Bucket=BUCKET, Key=columns_key)
        columns_data = json.loads(columns_obj["Body"].read())
        state["columns"] = columns_data["columns"]

        sample_key = f"{job['user_id']}/{job_id}/processed/sample.json"
        sample_obj = s3.get_object(Bucket=BUCKET, Key=sample_key)
        state["sample_data"] = json.loads(sample_obj["Body"].read())

    except Exception as e:
        print(f"Error loading job context: {e}")

    # Run transformation through the complete pipeline
    try:
        from agent_runtime.nodes.transformation_router import transformation_router_node
        from agent_runtime.nodes.dynamic_transformation_engine import (
            dynamic_transformation_executor_node,
            wait_for_transformation_node,
        )
        from agent_runtime.nodes.targeted_transformation_engine import (
            targeted_transformation_executor_node,
            wait_for_targeted_transformation_node
        )

        from agent_runtime.nodes.dynamic_template_detector import generate_template_files_node
        from agent_runtime.nodes.finalize_node import finalize_node

        # Step 1: Route to appropriate transformation type
        print("[apply_transformation] Step 1: Routing transformation...")
        state = transformation_router_node(state)

        next_node = state.get("next")
        print(f"[apply_transformation] Router decision: {next_node}")

        # Step 2: Execute appropriate transformation
        if next_node == "targeted_transformation":
            print("[apply_transformation] Step 2: Executing targeted transformation...")
            state = targeted_transformation_executor_node(state)

        elif next_node == "dynamic_transformation":
            print("[apply_transformation] Step 2: Executing full transformation...")
            state = dynamic_transformation_executor_node(state)

        else:
            print(f"[apply_transformation] Skipping transformation - next: {next_node}")
            state = finalize_node(state)
            return

        if "error" in state:
            print(f"❌ Transformation execution failed: {state['error']}")
            jobs_table.update_item(
                Key={"job_id": job_id},
                UpdateExpression="SET transformation_error = :e",
                ExpressionAttributeValues={":e": state["error"]},
            )
            return

        # Step 3: Wait for Glue job (if transformation was queued)
        next_step = state.get("next")

        if next_step == "wait_for_transformation":
            print("[apply_transformation] Step 3: Waiting for full transformation...")
            state = wait_for_transformation_node(state)

        elif next_step == "wait_for_targeted_transformation":
            print("[apply_transformation] Step 3: Waiting for targeted transformation...")
            state = wait_for_targeted_transformation_node(state)

        if "error" in state:
            print(f"❌ Transformation failed: {state['error']}")
            jobs_table.update_item(
                Key={"job_id": job_id},
                UpdateExpression="SET transformation_error = :e",
                ExpressionAttributeValues={":e": state["error"]},
            )
            return

        # Step 4: Regenerate templates if needed (only for full transformation)
        next_action = state.get("next")

        if next_action == "generate_template_files":
            print("[apply_transformation] Step 4: Regenerating ALL templates (full transformation)...")
            state = generate_template_files_node(state)
            print(f"   ✓ {len(state.get('template_files', []))} templates regenerated")
        else:
            # For targeted transformation, XLSX files already updated in Glue
            metadata = state.get("targeted_transformation_metadata", {})
            if metadata:
                affected = metadata.get("affected_templates", [])
                print(f"[apply_transformation] Step 4: Templates already updated in place: {affected}")

        # Step 5: Finalize
        print("[apply_transformation] Step 5: Finalizing...")
        state = finalize_node(state)

        # Check for clarification needed
        if state.get('clarification_needed'):
            print(f"❓ Clarification needed from user")
            clarification_msg = state.get('clarification_message', '')
            questions = state.get('clarification_questions', [])
            print(f"   Message: {clarification_msg}")
            print(f"   Questions: {len(questions)}")

            clarification_context = {
                'questions': questions,
                'message': clarification_msg,
                'original_request': transformation,
                'timestamp': datetime.now(timezone.utc).isoformat(),
            }

            jobs_table.update_item(
                Key={"job_id": job_id},
                UpdateExpression="SET transformation_status = :s, clarification_context = :c, updated_at = :u",
                ExpressionAttributeValues={
                    ":s": "NEEDS_CLARIFICATION",
                    ":c": json.dumps(clarification_context),
                    ":u": datetime.now(timezone.utc).isoformat(),
                },
            )
        else:
            print(f"   Transformed path: {state.get('transformed_path', 'N/A')}")
            print(f"   Template files: {len(state.get('template_files', []))}")

            jobs_table.update_item(
                Key={"job_id": job_id},
                UpdateExpression="SET last_transformation = :t, transformed_path = :p, transformation_status = :s, updated_at = :u",
                ExpressionAttributeValues={
                    ":t": transformation,
                    ":p": state.get("transformed_path", ""),
                    ":s": "COMPLETED",
                    ":u": datetime.now(timezone.utc).isoformat(),
                },
            )

    except Exception as e:
        print(f"[apply_transformation] ❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise e


if __name__ == "__main__":
    print("=" * 60)
    print("  EC2 SQS Worker - Excel Trace Agent")
    print("=" * 60)
    poll_queue()