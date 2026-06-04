"""
Local Development Mode - No AWS Required

This version uses in-memory storage for testing without AWS infrastructure.
Perfect for local development and testing the UI/UX.
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uuid
import json
from datetime import datetime
from typing import Dict
import time

app = FastAPI(title="Excel Trace Agent API (Local Mode)", version="1.0.0-local")

# CORS Configuration
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

# In-memory storage (replaces DynamoDB)
jobs_store: Dict[str, dict] = {}
files_store: Dict[str, bytes] = {}


@app.get("/")
async def root():
    return {
        "message": "Excel Trace Agent API (Local Mode)",
        "version": "1.0.0-local",
        "mode": "development",
        "note": "Using in-memory storage - no AWS required"
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "excel-trace-agent-local",
        "jobs_count": len(jobs_store),
        "files_count": len(files_store)
    }


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    """
    Upload Excel file (local mode - stores in memory)
    """

    user_id = "user_1"
    job_id = str(uuid.uuid4())

    try:
        # Read file content
        content = await file.read()

        # Validate file
        if len(content) > 500 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="File too large. Maximum size is 500MB.")

        if not file.filename.endswith(('.xlsx', '.xls')):
            raise HTTPException(status_code=400, detail="Invalid file type. Only .xlsx and .xls files are supported.")

        # Store file in memory
        file_key = f"{user_id}/{job_id}/raw/{file.filename}"
        files_store[file_key] = content

        # Create job record
        job = {
            "job_id": job_id,
            "user_id": user_id,
            "status": "UPLOADED",
            "s3_key": file_key,
            "filename": file.filename,
            "file_size": len(content),
            "created_at": datetime.utcnow().isoformat(),
            "current_step": "file_uploaded_successfully",
            "progress": 100,
            "mode": "local",
            "note": "Simulated - AWS not configured"
        }

        jobs_store[job_id] = job

        print(f"✅ File uploaded: {file.filename} ({len(content)} bytes)")
        print(f"   Job ID: {job_id}")

        return {
            "job_id": job_id,
            "message": "File uploaded successfully (local mode)",
            "filename": file.filename,
            "size": len(content),
            "note": "This is running in local mode. To process with AWS, deploy the infrastructure."
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@app.get("/job/{job_id}")
async def get_job_status(job_id: str):
    """
    Get job status (local mode)
    """

    if job_id not in jobs_store:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs_store[job_id]

    return {
        **job,
        "available_actions": [
            "Job uploaded successfully",
            "To process this file, deploy AWS infrastructure",
            "See DEPLOYMENT_GUIDE.md for setup instructions"
        ]
    }


@app.get("/jobs")
async def list_jobs():
    """
    List all jobs (local mode)
    """

    return {
        "jobs": list(jobs_store.values()),
        "total": len(jobs_store),
        "mode": "local"
    }


@app.post("/chat")
async def chat(message: dict):
    """
    Chat endpoint (local mode - simulated responses)
    """

    job_id = message.get("job_id")
    user_message = message.get("message", "")

    if job_id not in jobs_store:
        raise HTTPException(status_code=404, detail="Job not found")

    # Simulated response
    responses = {
        "templates": "In local mode, template detection requires AWS Bedrock. Deploy the infrastructure to use this feature.",
        "convert": "To execute transformations, deploy AWS Glue jobs. See DEPLOYMENT_GUIDE.md for instructions.",
        "status": f"Your file '{jobs_store[job_id]['filename']}' has been uploaded successfully. Deploy AWS infrastructure to process it.",
    }

    # Find matching response
    response_text = "I'm running in local mode without AWS services. To unlock full functionality (template detection, transformations, etc.), please deploy the AWS infrastructure. See DEPLOYMENT_GUIDE.md for step-by-step instructions."

    for keyword, resp in responses.items():
        if keyword.lower() in user_message.lower():
            response_text = resp
            break

    return {
        "job_id": job_id,
        "user_message": user_message,
        "assistant_response": response_text,
        "is_transformation": False,
        "mode": "local"
    }


@app.delete("/job/{job_id}")
async def delete_job(job_id: str):
    """
    Delete job (local mode)
    """

    if job_id not in jobs_store:
        raise HTTPException(status_code=404, detail="Job not found")

    # Remove from stores
    job = jobs_store.pop(job_id)
    file_key = job.get("s3_key")

    if file_key in files_store:
        files_store.pop(file_key)

    return {
        "message": "Job deleted successfully",
        "job_id": job_id
    }


@app.get("/stats")
async def get_stats():
    """
    Get system statistics
    """

    total_size = sum(len(content) for content in files_store.values())

    return {
        "mode": "local",
        "total_jobs": len(jobs_store),
        "total_files": len(files_store),
        "total_storage_bytes": total_size,
        "total_storage_mb": round(total_size / (1024 * 1024), 2),
        "uptime": "Running in local development mode",
        "aws_status": "Not configured - using in-memory storage"
    }


if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("🚀 Starting Excel Trace Agent in LOCAL MODE")
    print("=" * 60)
    print("✅ No AWS configuration required")
    print("✅ Files stored in memory")
    print("✅ Perfect for UI/UX testing")
    print("")
    print("⚠️  Note: Template detection and transformations require AWS")
    print("📖 See DEPLOYMENT_GUIDE.md for AWS setup")
    print("=" * 60)
    print("")
    uvicorn.run(app, host="0.0.0.0", port=8000)
