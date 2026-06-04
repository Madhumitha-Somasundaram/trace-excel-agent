from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import boto3
import uuid
import json
from datetime import datetime
from typing import Dict, List, Optional
import asyncio
from tools.llm import llm_call_streaming, llm_call
from models.user import User
from auth.dependencies import get_current_user, get_optional_user
from app.auth_endpoints import router as auth_router

app = FastAPI(title="Excel Trace Agent API", version="2.0.0")

# Include authentication routes
app.include_router(auth_router)

# CORS Configuration - Allow React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=3600,
)

s3 = boto3.client("s3", region_name="us-east-1")
sqs = boto3.client("sqs", region_name="us-east-1")
ddb = boto3.resource("dynamodb", region_name="us-east-1")

BUCKET = "excel-trace-agent-bucket-549955691461"
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


# Request/Response models
class ChatMessage(BaseModel):
    job_id: str
    message: str


class TransformationRequest(BaseModel):
    job_id: str
    transformation: str


@app.get("/")
async def root():
    return {"message": "Excel Trace Agent API with Authentication", "version": "2.0.0"}


@app.post("/upload")
async def upload(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """
    Upload Excel file for processing.

    **Authentication Required**

    The file is uploaded to S3 and queued for agent processing.
    """

    user_id = current_user.username
    job_id = str(uuid.uuid4())

    key = f"{user_id}/{job_id}/raw/{file.filename}"

    content = await file.read()

    # Validate file size (max 500MB)
    if len(content) > 500 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Maximum size is 500MB.")

    # Validate file extension
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
        "progress": 0
    })

    # Upload to S3
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=content
    )

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

    # Send SQS message
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
async def get_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get the current status of a job.

    **Authentication Required** - Only the job owner can view it.
    """

    try:
        response = table.get_item(Key={"job_id": job_id})

        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Job not found")

        job = response['Item']

        # Verify job ownership
        if job['user_id'] != current_user.username:
            raise HTTPException(status_code=403, detail="Access denied to this job")

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


@app.get("/jobs")
async def get_user_jobs(
    current_user: User = Depends(get_current_user),
    limit: int = 20
):
    """
    Get all jobs for the current user.

    **Authentication Required**
    """
    try:
        response = table.scan(
            FilterExpression="user_id = :user_id",
            ExpressionAttributeValues={":user_id": current_user.username},
            Limit=limit
        )

        jobs = response.get('Items', [])

        # Sort by created_at descending
        jobs.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return {
            "jobs": jobs,
            "count": len(jobs)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
async def chat(
    message: ChatMessage,
    current_user: User = Depends(get_current_user)
):
    """
    Chat interface for asking questions or requesting transformations.

    **Authentication Required**

    Examples:
    - "What templates did you find?"
    - "Convert distance from meters to kilometers"
    - "Calculate average salary by department"
    - "Show me data quality issues"
    """

    job_id = message.job_id
    user_message = message.message

    # Get job context
    try:
        from agent_runtime.conversation_memory import ConversationMemory

        response = table.get_item(Key={"job_id": job_id})

        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Job not found")

        job = response['Item']

        # Verify job ownership
        if job['user_id'] != current_user.username:
            raise HTTPException(status_code=403, detail="Access denied to this job")

        user_id = current_user.username

        if job['status'] != 'COMPLETED':
            return {
                "response": f"Job is still processing (status: {job['status']}). Please wait for completion before chatting.",
                "status": job['status']
            }

        # Initialize conversation memory
        conversation = ConversationMemory(job_id, user_id)

        # Check if there's a pending clarification
        pending_clarification = conversation.get_pending_clarification()
        if pending_clarification:
            user_lower = user_message.lower().strip()

            # User confirmed - mark as answered and let transformation proceed
            if any(kw in user_lower for kw in ['yes', 'proceed', 'go ahead', 'continue', 'ok', 'sure']):
                conversation.mark_clarification_answered()
                conversation.add_message('user', user_message)
                conversation.add_message('assistant', "Great! I'll proceed with the transformation.")

                return {
                    "job_id": job_id,
                    "user_message": user_message,
                    "assistant_response": "Great! I'll proceed with the transformation. This will take a few minutes.",
                    "is_transformation": False,
                    "clarification_confirmed": True,
                    "is_download_request": False
                }

            # User cancelled
            elif any(kw in user_lower for kw in ['no', 'cancel', 'stop', 'don\'t']):
                conversation.mark_clarification_answered()
                conversation.add_message('user', user_message)
                conversation.add_message('assistant', "Transformation cancelled.")

                return {
                    "job_id": job_id,
                    "user_message": user_message,
                    "assistant_response": "Transformation cancelled. Let me know if you'd like to do something else!",
                    "is_transformation": False,
                    "is_download_request": False
                }

        # Load job results for context
        results_key = job.get('results_key')
        if results_key:
            results_obj = s3.get_object(Bucket=BUCKET, Key=results_key)
            results = json.loads(results_obj['Body'].read())
        else:
            results = {}

        # Build context for LLM with conversation history
        conversation_history = conversation.get_conversation_context(max_messages=6)

        context_prompt = f"""You are a helpful data analysis assistant.

User uploaded an Excel file that has been processed. Here's what we found:

File: {job.get('filename', 'unknown')}
Rows: {results.get('profile', {}).get('total_rows', 0)}
Columns: {results.get('profile', {}).get('total_columns', 0)}

Templates detected: {json.dumps(results.get('templates', []), indent=2)}

Previous conversation:
{conversation_history}

User question: {user_message}

**Important intent detection:**
  - If user asks to "download", "get files", "give me templates", "export", etc. → is_download_request: true
  - If user requests transformation → is_transformation_request: true
  - Otherwise → just answer the question

Return JSON:
{{
  "response": "your response text",
  "is_transformation_request": true/false,
  "is_download_request": true/false,
  "transformation_type": "conversion|filtering|aggregation|cleaning|custom" (if applicable)
}}"""

        llm_response = llm_call(context_prompt, max_tokens=1024)

        # Add to conversation history
        conversation.add_message('user', user_message)

        # Handle download request
        if llm_response.get('is_download_request'):
            from app.download_endpoint import get_template_downloads
            downloads = get_template_downloads(job_id)

            response_text = llm_response.get('response', 'Here are your template files:')
            conversation.add_message('assistant', response_text)

            return {
                "job_id": job_id,
                "user_message": user_message,
                "assistant_response": response_text,
                "is_transformation": False,
                "is_download_request": True,
                "downloads": downloads
            }

        response_text = llm_response.get('response', '')
        conversation.add_message('assistant', response_text)

        return {
            "job_id": job_id,
            "user_message": user_message,
            "assistant_response": response_text,
            "is_transformation": llm_response.get('is_transformation_request', False),
            "transformation_type": llm_response.get('transformation_type'),
            "is_download_request": False
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/download-templates/{job_id}")
async def get_download_templates(
    job_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get downloadable template files for a job.

    **Authentication Required**

    Returns pre-signed S3 URLs for each template Excel file.
    """
    from app.download_endpoint import get_template_downloads

    try:
        # Verify job ownership
        response = table.get_item(Key={"job_id": job_id})
        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Job not found")

        job = response['Item']
        if job['user_id'] != current_user.username:
            raise HTTPException(status_code=403, detail="Access denied")

        template_files = get_template_downloads(job_id)

        return {
            "job_id": job_id,
            "template_count": len(template_files),
            "templates": template_files
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/transform")
async def request_transformation(
    req: TransformationRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Request a transformation to be applied to the processed data.

    **Authentication Required**

    This triggers the agent to generate and execute PySpark code.
    """

    job_id = req.job_id
    transformation = req.transformation

    # Verify job ownership
    response = table.get_item(Key={"job_id": job_id})
    if 'Item' not in response:
        raise HTTPException(status_code=404, detail="Job not found")

    job = response['Item']
    if job['user_id'] != current_user.username:
        raise HTTPException(status_code=403, detail="Access denied")

    # Queue transformation request
    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps({
            "job_id": job_id,
            "action": "transform",
            "transformation": transformation
        })
    )

    return {
        "message": "Transformation queued successfully",
        "job_id": job_id,
        "transformation": transformation
    }


@app.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    """
    WebSocket for real-time job updates.

    Connect to receive live updates as the agent processes your file.

    Note: WebSocket authentication can be added via query params or initial message
    """

    await manager.connect(job_id, websocket)

    try:
        while True:
            # Keep connection alive and listen for client messages
            data = await websocket.receive_text()

            # Client can send ping to keep alive
            if data == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(job_id)


@app.get("/templates/{job_id}")
async def get_templates(
    job_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get all generated templates for a job.

    **Authentication Required**

    Returns template metadata and download URLs.
    """

    try:
        response = table.get_item(Key={"job_id": job_id})

        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Job not found")

        job = response['Item']

        # Verify ownership
        if job['user_id'] != current_user.username:
            raise HTTPException(status_code=403, detail="Access denied")

        user_id = job['user_id']

        # Load template metadata
        metadata_key = f"{user_id}/{job_id}/templates/metadata.json"

        try:
            metadata_obj = s3.get_object(Bucket=BUCKET, Key=metadata_key)
            metadata = json.loads(metadata_obj['Body'].read())
            return metadata
        except s3.exceptions.NoSuchKey:
            return {"templates": [], "message": "No templates generated yet"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "excel-trace-agent", "version": "2.0.0"}
