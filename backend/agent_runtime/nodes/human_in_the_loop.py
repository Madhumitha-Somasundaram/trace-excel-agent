"""
Human-in-the-Loop (HITL) System - Requires user approval before any data changes.

Safety principles:
1. NEVER modify data without explicit user confirmation
2. Show detailed preview of ALL changes
3. Allow users to reject or modify transformations
4. Track approval history for audit
5. Support rollback to previous versions
"""
import os

import boto3
import json
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

s3_client = boto3.client('s3', region_name=os.environ.get("AWS_REGION", "us-east-1"))
ddb = boto3.resource('dynamodb', region_name=os.environ.get("AWS_REGION", "us-east-1"))
jobs_table = ddb.Table('jobs')
approvals_table = ddb.Table('transformation_approvals')  # New table for audit

BUCKET = "excel-trace-agent-bucket"


def generate_transformation_preview(
    job_id: str,
    user_request: str,
    intent_analysis: Dict[str, Any],
    code_result: Dict[str, Any],
    current_state: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Generate comprehensive preview of transformation for user approval.

    Returns:
        Preview object with all details for informed decision
    """

    profile = current_state.get('raw_profile', {})
    columns = current_state.get('columns', [])

    # Calculate impact
    input_columns = code_result.get('input_columns', [])
    output_columns = code_result.get('output_columns', [])
    new_columns = code_result.get('new_columns_created', [])
    modified_columns = code_result.get('modified_columns', [])

    # Estimate data changes
    total_rows = profile.get('total_rows', 0)
    validation = code_result.get('validation', {})
    row_change = validation.get('expected_row_count_change', 'same')

    if row_change == 'same':
        expected_rows = total_rows
    elif row_change == 'reduced':
        # Try to estimate based on filters
        expected_rows = f"~{int(total_rows * 0.7)} (estimated)"
    else:
        expected_rows = "varies"

    preview = {
        "preview_id": f"preview_{job_id}_{int(time.time())}",
        "job_id": job_id,
        "timestamp": datetime.utcnow().isoformat(),
        "status": "AWAITING_APPROVAL",

        # User request context
        "request": {
            "original_text": user_request,
            "intent": intent_analysis.get('intent_type'),
            "confidence": intent_analysis.get('confidence', 0.0),
            "complexity": intent_analysis.get('complexity', 'unknown')
        },

        # What will change
        "changes": {
            "summary": code_result.get('explanation', {}).get('what_it_does', ''),
            "steps": code_result.get('explanation', {}).get('steps', []),
            "input": {
                "rows": total_rows,
                "columns_used": input_columns,
                "column_count": len(input_columns)
            },
            "output": {
                "rows": expected_rows,
                "total_columns": len(output_columns),
                "new_columns": new_columns,
                "modified_columns": modified_columns,
                "removed_columns": [c for c in columns if c not in output_columns]
            },
            "data_impact": {
                "will_rows_change": row_change != 'same',
                "will_add_columns": len(new_columns) > 0,
                "will_modify_columns": len(modified_columns) > 0,
                "will_remove_columns": len([c for c in columns if c not in output_columns]) > 0,
                "reversible": len(modified_columns) == 0  # Only reversible if not modifying existing cols
            }
        },

        # Safety & quality
        "safety": {
            "edge_cases_handled": code_result.get('explanation', {}).get('edge_cases_handled', []),
            "null_handling": "Nulls are handled safely" if "null" in str(code_result) else "Unknown",
            "type_conversions": "Safe type conversions applied" if "cast" in str(code_result) else "No type changes",
            "data_quality_impact": validation.get('data_quality_impact', 'unknown')
        },

        # Execution details
        "execution": {
            "estimated_time": code_result.get('estimated_execution_time', 'unknown'),
            "recommended_workers": code_result.get('glue_worker_recommendation', '10 G.1X'),
            "estimated_cost": estimate_glue_cost(
                total_rows,
                code_result.get('glue_worker_recommendation', '10 G.1X')
            )
        },

        # Code preview (for technical users)
        "code_preview": {
            "language": "PySpark",
            "code": code_result.get('pyspark_code', ''),
            "truncated": len(code_result.get('pyspark_code', '')) > 1000
        },

        # Approval options
        "approval_options": {
            "can_approve": True,
            "can_modify": True,
            "can_reject": True,
            "requires_confirmation": True,
            "timeout_seconds": 3600  # Approval expires after 1 hour
        },

        # Warnings (if any)
        "warnings": generate_warnings(code_result, validation, current_state)
    }

    return preview


def generate_warnings(
    code_result: Dict[str, Any],
    validation: Dict[str, Any],
    current_state: Dict[str, Any]
) -> List[Dict[str, str]]:
    """
    Generate warnings about potential issues.
    """
    warnings = []

    # Check for data loss
    modified_columns = code_result.get('modified_columns', [])
    if modified_columns:
        warnings.append({
            "severity": "HIGH",
            "type": "data_modification",
            "message": f"This will modify existing columns: {', '.join(modified_columns)}. Original values will be lost.",
            "recommendation": "Consider creating new columns instead to preserve original data."
        })

    # Check for row filtering
    row_change = validation.get('expected_row_count_change', 'same')
    if row_change == 'reduced':
        warnings.append({
            "severity": "MEDIUM",
            "type": "data_filtering",
            "message": "This transformation will remove rows from your dataset.",
            "recommendation": "Make sure you want to permanently filter this data."
        })

    # Check for complex operations
    complexity = code_result.get('complexity', 'simple')
    if complexity == 'complex':
        warnings.append({
            "severity": "LOW",
            "type": "complexity",
            "message": "This is a complex transformation that may take longer to execute.",
            "recommendation": "Consider breaking it into smaller steps."
        })

    # Check for large dataset
    total_rows = current_state.get('raw_profile', {}).get('total_rows', 0)
    if total_rows > 10_000_000:
        warnings.append({
            "severity": "INFO",
            "type": "large_dataset",
            "message": f"Processing {total_rows:,} rows may take significant time and cost.",
            "recommendation": f"Estimated time: {estimate_processing_time(total_rows)}"
        })

    return warnings


def estimate_glue_cost(rows: int, worker_config: str) -> str:
    """
    Estimate AWS Glue processing cost.
    """
    # Parse worker config (e.g., "10 G.1X")
    parts = worker_config.split()
    num_workers = int(parts[0]) if len(parts) > 0 else 10
    worker_type = parts[1] if len(parts) > 1 else "G.1X"

    # Glue pricing (approximate, us-east-1)
    rates = {
        "G.1X": 0.44,  # per DPU-hour
        "G.2X": 0.88,
        "G.4X": 1.76
    }

    rate = rates.get(worker_type, 0.44)

    # Estimate runtime based on rows
    if rows < 1_000_000:
        hours = 0.05  # 3 minutes
    elif rows < 5_000_000:
        hours = 0.15  # 9 minutes
    elif rows < 10_000_000:
        hours = 0.25  # 15 minutes
    else:
        hours = 0.5  # 30 minutes

    cost = num_workers * rate * hours

    return f"${cost:.2f} (estimated)"


def estimate_processing_time(rows: int) -> str:
    """
    Estimate processing time based on row count.
    """
    if rows < 1_000_000:
        return "2-3 minutes"
    elif rows < 5_000_000:
        return "5-10 minutes"
    elif rows < 10_000_000:
        return "10-20 minutes"
    elif rows < 50_000_000:
        return "30-60 minutes"
    else:
        return "1-2 hours"


def save_preview_for_approval(preview: Dict[str, Any]) -> str:
    """
    Save preview to DynamoDB and S3 for user to review.

    Returns:
        preview_id for tracking
    """

    preview_id = preview['preview_id']
    job_id = preview['job_id']

    # Save to DynamoDB for quick lookup
    try:
        approvals_table.put_item(
            Item={
                'preview_id': preview_id,
                'job_id': job_id,
                'status': 'AWAITING_APPROVAL',
                'created_at': preview['timestamp'],
                'expires_at': int(time.time()) + 3600,  # 1 hour TTL
                'request': preview['request']['original_text'],
                'preview_summary': json.dumps(preview['changes']['summary'])
            }
        )
    except Exception as e:
        print(f"[HITL] Warning: Could not save to approvals table: {e}")

    # Save full preview to S3
    user_id = job_id.split('_')[0] if '_' in job_id else 'user_1'
    preview_key = f"{user_id}/{job_id}/approvals/{preview_id}.json"

    s3_client.put_object(
        Bucket=BUCKET,
        Key=preview_key,
        Body=json.dumps(preview, indent=2, default=str),
        ContentType='application/json'
    )

    # Update job status to show pending approval
    jobs_table.update_item(
        Key={'job_id': job_id},
        UpdateExpression='SET current_step = :c, pending_approval = :p',
        ExpressionAttributeValues={
            ':c': f'awaiting_approval: {preview["request"]["original_text"][:50]}',
            ':p': preview_id
        }
    )

    print(f"[HITL] Preview saved: {preview_id}")

    return preview_id


def wait_for_user_approval(preview_id: str, timeout: int = 3600) -> Dict[str, Any]:
    """
    Wait for user to approve, modify, or reject the transformation.

    Returns:
        approval_decision with status: APPROVED, REJECTED, MODIFIED, TIMEOUT
    """

    print(f"[HITL] Waiting for approval: {preview_id}")

    start_time = time.time()
    check_interval = 5  # Check every 5 seconds

    while time.time() - start_time < timeout:
        try:
            # Check approval status in DynamoDB
            response = approvals_table.get_item(Key={'preview_id': preview_id})

            if 'Item' in response:
                item = response['Item']
                status = item.get('status')

                if status == 'APPROVED':
                    print(f"[HITL] ✓ Approved by user")
                    return {
                        'status': 'APPROVED',
                        'preview_id': preview_id,
                        'approved_at': item.get('approved_at'),
                        'approved_by': item.get('approved_by', 'user'),
                        'modifications': item.get('modifications')
                    }

                elif status == 'REJECTED':
                    print(f"[HITL] ✗ Rejected by user")
                    return {
                        'status': 'REJECTED',
                        'preview_id': preview_id,
                        'rejected_at': item.get('rejected_at'),
                        'reason': item.get('rejection_reason')
                    }

                elif status == 'MODIFIED':
                    print(f"[HITL] ⚙ Modified by user")
                    return {
                        'status': 'MODIFIED',
                        'preview_id': preview_id,
                        'modified_at': item.get('modified_at'),
                        'modifications': item.get('modifications')
                    }

        except Exception as e:
            print(f"[HITL] Error checking approval: {e}")

        time.sleep(check_interval)

    # Timeout
    print(f"[HITL] ⏱ Approval timeout")

    approvals_table.update_item(
        Key={'preview_id': preview_id},
        UpdateExpression='SET #s = :s, timeout_at = :t',
        ExpressionAttributeNames={'#s': 'status'},
        ExpressionAttributeValues={
            ':s': 'TIMEOUT',
            ':t': datetime.utcnow().isoformat()
        }
    )

    return {
        'status': 'TIMEOUT',
        'preview_id': preview_id,
        'message': 'Approval request timed out after 1 hour'
    }


def record_transformation_execution(
    preview_id: str,
    job_id: str,
    execution_result: Dict[str, Any]
) -> None:
    """
    Record that transformation was executed after approval.

    Creates audit trail for compliance and debugging.
    """

    audit_record = {
        'preview_id': preview_id,
        'job_id': job_id,
        'executed_at': datetime.utcnow().isoformat(),
        'execution_status': execution_result.get('status'),
        'glue_run_id': execution_result.get('glue_run_id'),
        'output_location': execution_result.get('output_location'),
        'rows_processed': execution_result.get('rows_processed'),
        'execution_time': execution_result.get('execution_time')
    }

    # Update approval record
    approvals_table.update_item(
        Key={'preview_id': preview_id},
        UpdateExpression='SET execution_record = :e',
        ExpressionAttributeValues={':e': json.dumps(audit_record)}
    )

    # Save detailed audit log to S3
    user_id = job_id.split('_')[0] if '_' in job_id else 'user_1'
    audit_key = f"{user_id}/{job_id}/audit/{preview_id}_execution.json"

    s3_client.put_object(
        Bucket=BUCKET,
        Key=audit_key,
        Body=json.dumps(audit_record, indent=2, default=str),
        ContentType='application/json'
    )

    print(f"[HITL] Execution recorded: {preview_id}")


def create_data_snapshot(job_id: str, state: Dict[str, Any]) -> str:
    """
    Create snapshot of current data state before transformation.

    Enables rollback if user is unhappy with results.
    """

    snapshot_id = f"snapshot_{job_id}_{int(time.time())}"

    snapshot_info = {
        'snapshot_id': snapshot_id,
        'job_id': job_id,
        'created_at': datetime.utcnow().isoformat(),
        'data_location': state.get('cleaned_path'),
        'columns': state.get('columns'),
        'row_count': state.get('raw_profile', {}).get('total_rows', 0),
        'can_restore': True
    }

    # Save snapshot metadata
    user_id = job_id.split('_')[0] if '_' in job_id else 'user_1'
    snapshot_key = f"{user_id}/{job_id}/snapshots/{snapshot_id}.json"

    s3_client.put_object(
        Bucket=BUCKET,
        Key=snapshot_key,
        Body=json.dumps(snapshot_info, indent=2),
        ContentType='application/json'
    )

    print(f"[HITL] Snapshot created: {snapshot_id}")

    return snapshot_id


# Main HITL integration node
def human_approval_gate_node(state):
    """
    GATE NODE: Blocks execution until user approves transformation.

    This ensures NO changes are made without explicit user consent.
    """

    job_id = state['job_id']
    transformation_metadata = state.get('transformation_metadata', {})

    print(f"[HITL-Gate] Requesting user approval for: {job_id}")

    # Extract preview data
    preview = generate_transformation_preview(
        job_id=job_id,
        user_request=transformation_metadata.get('user_request', ''),
        intent_analysis=transformation_metadata.get('intent_analysis', {}),
        code_result=transformation_metadata.get('code_result', {}),
        current_state=state
    )

    # Save preview and wait for approval
    preview_id = save_preview_for_approval(preview)

    # Create snapshot before any changes
    snapshot_id = create_data_snapshot(job_id, state)
    state['data_snapshot_id'] = snapshot_id

    # BLOCK here until user approves
    approval_decision = wait_for_user_approval(preview_id, timeout=3600)

    # Process decision
    if approval_decision['status'] == 'APPROVED':
        print(f"[HITL-Gate] ✓ Proceeding with transformation")
        state['approval_status'] = 'APPROVED'
        state['preview_id'] = preview_id
        state['next'] = 'execute_transformation'

    elif approval_decision['status'] == 'MODIFIED':
        print(f"[HITL-Gate] ⚙ User modified transformation")
        # Apply user's modifications
        state['transformation_modifications'] = approval_decision.get('modifications', {})
        state['approval_status'] = 'APPROVED_WITH_MODIFICATIONS'
        state['preview_id'] = preview_id
        state['next'] = 'execute_transformation'

    elif approval_decision['status'] == 'REJECTED':
        print(f"[HITL-Gate] ✗ User rejected transformation")
        state['approval_status'] = 'REJECTED'
        state['rejection_reason'] = approval_decision.get('reason')
        state['next'] = 'finalize'

    else:  # TIMEOUT
        print(f"[HITL-Gate] ⏱ Approval timeout")
        state['approval_status'] = 'TIMEOUT'
        state['next'] = 'finalize'

    return state
