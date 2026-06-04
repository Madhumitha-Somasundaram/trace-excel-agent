"""
Approval API Endpoints - User reviews and approves/rejects transformations.
"""

from fastapi import HTTPException
from pydantic import BaseModel
import boto3
import json
from typing import Optional, List, Dict, Any
from datetime import datetime

s3_client = boto3.client('s3')
ddb = boto3.resource('dynamodb')
jobs_table = ddb.Table('jobs')
approvals_table = ddb.Table('transformation_approvals')

BUCKET = "excel-trace-agent-bucket"


class ApprovalDecision(BaseModel):
    preview_id: str
    decision: str  # "approve", "reject", "modify"
    rejection_reason: Optional[str] = None
    modifications: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = "user_1"


class ModificationRequest(BaseModel):
    preview_id: str
    field: str  # What to modify
    value: Any  # New value
    reason: Optional[str] = None


async def get_pending_approvals(job_id: str):
    """
    Get all pending approval requests for a job.

    GET /job/{job_id}/approvals
    """

    try:
        # Get job info
        response = jobs_table.get_item(Key={"job_id": job_id})

        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Job not found")

        job = response['Item']
        pending_preview_id = job.get('pending_approval')

        if not pending_preview_id:
            return {
                "job_id": job_id,
                "pending_approvals": [],
                "message": "No pending approvals"
            }

        # Load preview from S3
        user_id = job.get('user_id', 'user_1')
        preview_key = f"{user_id}/{job_id}/approvals/{pending_preview_id}.json"

        try:
            preview_obj = s3_client.get_object(Bucket=BUCKET, Key=preview_key)
            preview = json.loads(preview_obj['Body'].read())

            return {
                "job_id": job_id,
                "pending_approvals": [preview],
                "count": 1
            }

        except s3_client.exceptions.NoSuchKey:
            return {
                "job_id": job_id,
                "pending_approvals": [],
                "message": "Preview not found"
            }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_approval_preview(preview_id: str):
    """
    Get detailed preview for a specific approval request.

    GET /approvals/{preview_id}
    """

    try:
        # Get from DynamoDB first
        response = approvals_table.get_item(Key={'preview_id': preview_id})

        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Preview not found")

        approval_item = response['Item']
        job_id = approval_item['job_id']

        # Load full preview from S3
        user_id = job_id.split('_')[0] if '_' in job_id else 'user_1'
        preview_key = f"{user_id}/{job_id}/approvals/{preview_id}.json"

        preview_obj = s3_client.get_object(Bucket=BUCKET, Key=preview_key)
        preview = json.loads(preview_obj['Body'].read())

        # Add current status
        preview['current_status'] = approval_item.get('status', 'AWAITING_APPROVAL')

        return preview

    except s3_client.exceptions.NoSuchKey:
        raise HTTPException(status_code=404, detail="Preview not found in S3")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def submit_approval_decision(decision: ApprovalDecision):
    """
    Submit approval decision (approve/reject/modify).

    POST /approvals/decide
    """

    preview_id = decision.preview_id
    user_decision = decision.decision.lower()

    try:
        # Verify preview exists
        response = approvals_table.get_item(Key={'preview_id': preview_id})

        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Preview not found")

        approval_item = response['Item']

        # Check if already decided
        current_status = approval_item.get('status')
        if current_status not in ['AWAITING_APPROVAL', 'PENDING']:
            raise HTTPException(
                status_code=400,
                detail=f"This approval has already been {current_status.lower()}"
            )

        # Process decision
        timestamp = datetime.utcnow().isoformat()

        if user_decision == 'approve':
            # Approve the transformation
            approvals_table.update_item(
                Key={'preview_id': preview_id},
                UpdateExpression='SET #s = :s, approved_at = :t, approved_by = :u',
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues={
                    ':s': 'APPROVED',
                    ':t': timestamp,
                    ':u': decision.user_id
                }
            )

            return {
                "status": "approved",
                "preview_id": preview_id,
                "message": "Transformation approved. Execution will begin shortly.",
                "approved_at": timestamp
            }

        elif user_decision == 'reject':
            # Reject the transformation
            reason = decision.rejection_reason or "User rejected"

            approvals_table.update_item(
                Key={'preview_id': preview_id},
                UpdateExpression='SET #s = :s, rejected_at = :t, rejection_reason = :r',
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues={
                    ':s': 'REJECTED',
                    ':t': timestamp,
                    ':r': reason
                }
            )

            # Update job status
            job_id = approval_item['job_id']
            jobs_table.update_item(
                Key={'job_id': job_id},
                UpdateExpression='SET current_step = :c, pending_approval = :p',
                ExpressionAttributeValues={
                    ':c': 'transformation_rejected',
                    ':p': None
                }
            )

            return {
                "status": "rejected",
                "preview_id": preview_id,
                "message": "Transformation rejected.",
                "reason": reason,
                "rejected_at": timestamp
            }

        elif user_decision == 'modify':
            # User wants to modify the transformation
            if not decision.modifications:
                raise HTTPException(
                    status_code=400,
                    detail="Modifications must be provided when decision is 'modify'"
                )

            approvals_table.update_item(
                Key={'preview_id': preview_id},
                UpdateExpression='SET #s = :s, modified_at = :t, modifications = :m',
                ExpressionAttributeNames={'#s': 'status'},
                ExpressionAttributeValues={
                    ':s': 'MODIFIED',
                    ':t': timestamp,
                    ':m': json.dumps(decision.modifications)
                }
            )

            return {
                "status": "modified",
                "preview_id": preview_id,
                "message": "Transformation modified. Processing with your changes.",
                "modifications": decision.modifications,
                "modified_at": timestamp
            }

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid decision: {user_decision}. Must be 'approve', 'reject', or 'modify'"
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_approval_history(job_id: str):
    """
    Get history of all approvals/rejections for a job.

    GET /job/{job_id}/approval-history
    """

    try:
        # Query DynamoDB for all approval records for this job
        response = approvals_table.query(
            IndexName='job_id-index',  # GSI on job_id
            KeyConditionExpression='job_id = :jid',
            ExpressionAttributeValues={':jid': job_id}
        )

        history = []
        for item in response.get('Items', []):
            history.append({
                'preview_id': item.get('preview_id'),
                'request': item.get('request'),
                'status': item.get('status'),
                'created_at': item.get('created_at'),
                'approved_at': item.get('approved_at'),
                'rejected_at': item.get('rejected_at'),
                'rejection_reason': item.get('rejection_reason'),
                'execution_record': item.get('execution_record')
            })

        # Sort by creation time (newest first)
        history.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return {
            "job_id": job_id,
            "history": history,
            "total_count": len(history)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def request_modification(modification: ModificationRequest):
    """
    Request a specific modification to the transformation.

    POST /approvals/{preview_id}/modify
    """

    preview_id = modification.preview_id

    try:
        # Load current preview
        response = approvals_table.get_item(Key={'preview_id': preview_id})

        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Preview not found")

        approval_item = response['Item']
        job_id = approval_item['job_id']

        # Load full preview from S3
        user_id = job_id.split('_')[0] if '_' in job_id else 'user_1'
        preview_key = f"{user_id}/{job_id}/approvals/{preview_id}.json"

        preview_obj = s3_client.get_object(Bucket=BUCKET, Key=preview_key)
        preview = json.loads(preview_obj['Body'].read())

        # Apply modification
        modifications = preview.get('modifications', {})
        modifications[modification.field] = {
            'value': modification.value,
            'reason': modification.reason,
            'modified_at': datetime.utcnow().isoformat()
        }

        preview['modifications'] = modifications

        # Save updated preview
        s3_client.put_object(
            Bucket=BUCKET,
            Key=preview_key,
            Body=json.dumps(preview, indent=2, default=str),
            ContentType='application/json'
        )

        return {
            "preview_id": preview_id,
            "message": f"Modified {modification.field}",
            "new_value": modification.value,
            "modifications": modifications
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def cancel_approval_request(preview_id: str):
    """
    Cancel a pending approval request.

    DELETE /approvals/{preview_id}
    """

    try:
        response = approvals_table.get_item(Key={'preview_id': preview_id})

        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Preview not found")

        approval_item = response['Item']

        # Only allow canceling if still pending
        if approval_item.get('status') not in ['AWAITING_APPROVAL', 'PENDING']:
            raise HTTPException(
                status_code=400,
                detail="Cannot cancel - approval already processed"
            )

        # Update status to cancelled
        approvals_table.update_item(
            Key={'preview_id': preview_id},
            UpdateExpression='SET #s = :s, cancelled_at = :t',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':s': 'CANCELLED',
                ':t': datetime.utcnow().isoformat()
            }
        )

        # Update job
        job_id = approval_item['job_id']
        jobs_table.update_item(
            Key={'job_id': job_id},
            UpdateExpression='SET pending_approval = :p',
            ExpressionAttributeValues={':p': None}
        )

        return {
            "preview_id": preview_id,
            "message": "Approval request cancelled",
            "cancelled_at": datetime.utcnow().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
