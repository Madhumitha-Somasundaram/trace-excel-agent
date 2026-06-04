"""
Enhanced FastAPI Application with Human-in-the-Loop Approvals.

Key additions:
- Approval preview endpoints
- Approve/Reject/Modify endpoints
- Approval history tracking
- Real-time approval status via WebSocket
"""

from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import boto3
import uuid
import json
from datetime import datetime
from typing import Dict, List, Optional
import asyncio

# Import approval endpoints
from app.approval_endpoints import (
    ApprovalDecision,
    get_pending_approvals,
    get_approval_preview,
    submit_approval_decision,
    get_approval_history,
    cancel_approval_request
)

app = FastAPI(title="Excel Trace Agent API with HITL", version="2.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

s3 = boto3.client("s3")
sqs = boto3.client("sqs")
ddb = boto3.resource("dynamodb")

BUCKET = "excel-trace-agent-bucket"
QUEUE_URL = "https://sqs.us-east-1.amazonaws.com/549955691461/excel-trace-queue"
table = ddb.Table("jobs")

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, job_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[job_id] = websocket

    def disconnect(self, job_id: str):
        if job_id in self.active_connections:
            del self.active_connections[job_id]

    async def send_message(self, job_id: str, message: dict):
        if job_id in self.active_connections:
            await self.active_connections[job_id].send_json(message)

manager = ConnectionManager()


# ========== EXISTING ENDPOINTS (enhanced) ==========

@app.get("/")
async def root():
    return {
        "message": "Excel Trace Agent API with Human-in-the-Loop",
        "version": "2.0.0",
        "features": [
            "Dynamic template detection",
            "LLM-driven transformations",
            "Human approval required",
            "Audit trail",
            "Data snapshots"
        ]
    }


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    """Upload Excel file (unchanged from v1)"""

    user_id = "user_1"
    job_id = str(uuid.uuid4())
    key = f"{user_id}/{job_id}/raw/{file.filename}"

    content = await file.read()

    if len(content) > 500 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 500MB.")

    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Invalid file type. Only .xlsx and .xls files are supported.")

    table.put_item(Item={
        "job_id": job_id,
        "user_id": user_id,
        "status": "UPLOADING",
        "s3_key": key,
        "filename": file.filename,
        "file_size": len(content),
        "created_at": datetime.utcnow().isoformat(),
        "current_step": "upload_started",
        "progress": 0,
        "requires_approval": True  # NEW: Flag for HITL
    })

    s3.put_object(Bucket=BUCKET, Key=key, Body=content)

    table.update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET #s = :s, current_step = :c, progress = :p",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": "UPLOADED",
            ":c": "queued_to_sqs",
            ":p": 5
        }
    )

    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps({
            "user_id": user_id,
            "job_id": job_id,
            "s3_key": key
        })
    )

    return {
        "job_id": job_id,
        "message": "File uploaded and queued successfully",
        "filename": file.filename,
        "size": len(content)
    }


@app.get("/job/{job_id}")
async def get_job_status(job_id: str):
    """Get job status with approval info"""

    try:
        response = table.get_item(Key={"job_id": job_id})

        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Job not found")

        job = response['Item']

        # Add approval status if applicable
        if job.get('pending_approval'):
            job['requires_user_action'] = True
            job['action_url'] = f"/approvals/{job['pending_approval']}"

        # If job is complete, fetch results
        if job['status'] == 'COMPLETED' and 'results_key' in job:
            try:
                results_obj = s3.get_object(Bucket=BUCKET, Key=job['results_key'])
                results = json.loads(results_obj['Body'].read())
                job['results'] = results
            except Exception as e:
                print(f"Error loading results: {e}")

        return job

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== NEW HITL ENDPOINTS ==========

@app.get("/job/{job_id}/approvals")
async def get_job_approvals(job_id: str):
    """
    Get all pending approval requests for a job.

    Returns preview of transformations awaiting user decision.
    """
    return await get_pending_approvals(job_id)


@app.get("/approvals/{preview_id}")
async def get_preview(preview_id: str):
    """
    Get detailed transformation preview for review.

    Shows:
    - What will change
    - Impact analysis
    - Warnings
    - Estimated cost/time
    - Generated code (optional)
    """
    return await get_approval_preview(preview_id)


@app.post("/approvals/decide")
async def decide_on_approval(decision: ApprovalDecision):
    """
    Submit approval decision.

    Decisions:
    - approve: Execute transformation as shown
    - reject: Cancel transformation
    - modify: Execute with user modifications

    Example:
    {
      "preview_id": "preview_123",
      "decision": "approve"
    }
    """
    result = await submit_approval_decision(decision)

    # Notify via WebSocket if connected
    if 'job_id' in result:
        await manager.send_message(result['job_id'], {
            "type": "approval_decision",
            "status": result['status'],
            "message": result['message']
        })

    return result


@app.get("/job/{job_id}/approval-history")
async def get_history(job_id: str):
    """
    Get complete approval history for audit purposes.

    Shows all transformations: approved, rejected, executed.
    """
    return await get_approval_history(job_id)


@app.delete("/approvals/{preview_id}")
async def cancel_approval(preview_id: str):
    """
    Cancel a pending approval request.

    Only works if approval is still pending.
    """
    return await cancel_approval_request(preview_id)


@app.post("/approvals/{preview_id}/simulate")
async def simulate_transformation(preview_id: str):
    """
    Run transformation on sample data (first 1000 rows) to preview results.

    Helps users understand what will happen before approving.
    """
    # TODO: Implement simulation on sample
    return {
        "preview_id": preview_id,
        "message": "Simulation feature coming soon",
        "status": "not_implemented"
    }


# ========== CHAT ENDPOINTS (enhanced) ==========

@app.post("/chat")
async def chat(message: dict):
    """
    Enhanced chat that creates approval requests for transformations.

    Flow:
    1. User sends message
    2. System analyzes intent
    3. If transformation: Generate preview → Create approval request
    4. If question: Answer directly
    """

    from app.enhanced_chat_endpoint import enhanced_chat

    chat_result = await enhanced_chat(message)

    # If it's a transformation, create approval request automatically
    if chat_result.get('type') == 'transformation_preview':
        # Already saved in enhanced_chat
        pass

    return chat_result


# ========== WEBSOCKET ==========

@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """
    WebSocket for real-time updates including approval requests.

    Messages:
    - status_update: Job progress
    - approval_requested: New approval needed
    - approval_decision: User decided
    - transformation_complete: Transformation done
    """

    await manager.connect(job_id, websocket)

    try:
        while True:
            data = await websocket.receive_text()

            if data == "ping":
                await websocket.send_json({"type": "pong"})
            elif data == "get_status":
                # Send current status
                job = table.get_item(Key={"job_id": job_id}).get('Item')
                if job:
                    await websocket.send_json({
                        "type": "status",
                        "status": job.get('status'),
                        "step": job.get('current_step'),
                        "progress": job.get('progress'),
                        "pending_approval": job.get('pending_approval')
                    })

    except WebSocketDisconnect:
        manager.disconnect(job_id)


# ========== HEALTH & DOCS ==========

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "excel-trace-agent-hitl",
        "version": "2.0.0"
    }


@app.get("/features")
async def list_features():
    """List all HITL features."""
    return {
        "human_in_the_loop": {
            "enabled": True,
            "features": [
                "Transformation preview before execution",
                "Approve/Reject/Modify decisions",
                "Detailed impact analysis",
                "Cost and time estimates",
                "Safety warnings",
                "Audit trail",
                "Data snapshots for rollback"
            ]
        },
        "dynamic_system": {
            "enabled": True,
            "features": [
                "Multi-template detection",
                "LLM-driven transformations",
                "No static rules",
                "Adaptive to any domain"
            ]
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
