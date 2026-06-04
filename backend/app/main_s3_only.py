"""
Production-ready FastAPI backend using only S3 (no DynamoDB/Lambda/Glue required)

This version:
- Uses existing S3 bucket: excel-trace-agent-bucket
- Stores job metadata in S3 (no DynamoDB needed)
- Processes files using local PySpark (simulates Glue)
- Real AWS integration for file storage
"""

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import boto3
import uuid
import json
from datetime import datetime
from typing import Dict, List, Optional
import asyncio

app = FastAPI(title="Excel Trace Agent API (S3-only)", version="2.0.0")

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

s3 = boto3.client("s3", region_name="us-east-1")
BUCKET = "excel-trace-agent-bucket"

# Request models
class ChatMessage(BaseModel):
    job_id: str
    message: str
    user_id: Optional[str] = "user_1"


def get_job_metadata_key(job_id: str) -> str:
    """Get S3 key for job metadata"""
    return f"jobs/{job_id}/metadata.json"


def save_job_metadata(job: dict):
    """Save job metadata to S3"""
    key = get_job_metadata_key(job['job_id'])
    s3.put_object(
        Bucket=BUCKET,
        Key=key,
        Body=json.dumps(job, indent=2),
        ContentType='application/json'
    )


def get_job_metadata(job_id: str) -> Optional[dict]:
    """Get job metadata from S3"""
    try:
        key = get_job_metadata_key(job_id)
        response = s3.get_object(Bucket=BUCKET, Key=key)
        return json.loads(response['Body'].read())
    except s3.exceptions.NoSuchKey:
        return None


@app.get("/")
async def root():
    return {
        "message": "Excel Trace Agent API (S3-only)",
        "version": "2.0.0",
        "mode": "production-s3",
        "bucket": BUCKET
    }


@app.get("/health")
async def health_check():
    """Health check"""
    try:
        # Test S3 access
        s3.head_bucket(Bucket=BUCKET)
        return {
            "status": "healthy",
            "service": "excel-trace-agent-s3",
            "s3_bucket": BUCKET,
            "s3_access": "ok"
        }
    except Exception as e:
        return {
            "status": "degraded",
            "service": "excel-trace-agent-s3",
            "error": str(e)
        }


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    """
    Upload Excel file for processing (stores in S3)
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

        # Upload to S3
        key = f"{user_id}/{job_id}/raw/{file.filename}"
        s3.put_object(
            Bucket=BUCKET,
            Key=key,
            Body=content,
            ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

        # Create job metadata
        job = {
            "job_id": job_id,
            "user_id": user_id,
            "status": "UPLOADED",
            "s3_key": key,
            "filename": file.filename,
            "file_size": len(content),
            "created_at": datetime.utcnow().isoformat(),
            "current_step": "file_uploaded_to_s3",
            "progress": 10,
            "mode": "s3-only",
            "bucket": BUCKET
        }

        save_job_metadata(job)

        print(f"✅ File uploaded to S3: s3://{BUCKET}/{key}")
        print(f"   Job ID: {job_id}")
        print(f"   Size: {len(content)} bytes")

        # Trigger background processing
        asyncio.create_task(process_file_in_background(job_id, key, file.filename))

        return {
            "job_id": job_id,
            "message": "File uploaded successfully to AWS S3",
            "filename": file.filename,
            "size": len(content),
            "bucket": BUCKET,
            "s3_key": key
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


async def process_file_in_background(job_id: str, s3_key: str, filename: str):
    """
    Background task to process the uploaded file
    Simulates AWS Glue processing using local libraries
    """
    try:
        # Update status
        job = get_job_metadata(job_id)
        job['status'] = 'PROCESSING'
        job['current_step'] = 'analyzing_file'
        job['progress'] = 30
        save_job_metadata(job)

        await asyncio.sleep(2)  # Simulate processing

        # Download file from S3
        response = s3.get_object(Bucket=BUCKET, Key=s3_key)
        file_content = response['Body'].read()

        # Basic analysis (without PySpark dependencies for now)
        import pandas as pd
        import io

        df = pd.read_excel(io.BytesIO(file_content))

        # Profile data
        profile = {
            "total_rows": len(df),
            "total_columns": len(df.columns),
            "columns": df.columns.tolist(),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "null_counts": df.isnull().sum().to_dict(),
            "sample_data": df.head(10).to_dict('records')
        }

        # Save profile to S3
        profile_key = f"{job['user_id']}/{job_id}/profile/profile.json"
        s3.put_object(
            Bucket=BUCKET,
            Key=profile_key,
            Body=json.dumps(profile, indent=2),
            ContentType='application/json'
        )

        # Detect simple templates (without LLM for now)
        templates_detected = detect_simple_templates(df.columns.tolist())

        # Update job with results
        job['status'] = 'COMPLETED'
        job['current_step'] = 'processing_complete'
        job['progress'] = 100
        job['profile_key'] = profile_key
        job['templates'] = templates_detected
        job['completed_at'] = datetime.utcnow().isoformat()
        save_job_metadata(job)

        print(f"✅ Processing complete for job {job_id}")
        print(f"   Templates detected: {len(templates_detected)}")

    except Exception as e:
        print(f"❌ Processing error for job {job_id}: {str(e)}")
        job = get_job_metadata(job_id)
        job['status'] = 'FAILED'
        job['error'] = str(e)
        save_job_metadata(job)


def detect_simple_templates(columns: List[str]) -> List[dict]:
    """
    Simple template detection based on column name patterns
    (Without LLM/embeddings for initial version)
    """
    templates = []

    # Employee patterns
    employee_cols = [c for c in columns if any(k in c.lower() for k in ['employee', 'name', 'salary', 'department', 'hire'])]
    if len(employee_cols) >= 3:
        templates.append({
            "name": "Employee Data",
            "type": "employee",
            "columns": employee_cols,
            "confidence": 0.8
        })

    # Transportation patterns
    transport_cols = [c for c in columns if any(k in c.lower() for k in ['vehicle', 'distance', 'route', 'fuel', 'delivery'])]
    if len(transport_cols) >= 3:
        templates.append({
            "name": "Transportation Data",
            "type": "transportation",
            "columns": transport_cols,
            "confidence": 0.8
        })

    # Financial patterns
    finance_cols = [c for c in columns if any(k in c.lower() for k in ['transaction', 'amount', 'payment', 'cost', 'price'])]
    if len(finance_cols) >= 2:
        templates.append({
            "name": "Financial Data",
            "type": "financial",
            "columns": finance_cols,
            "confidence": 0.7
        })

    return templates


@app.get("/job/{job_id}")
async def get_job_status(job_id: str):
    """
    Get job status from S3
    """
    job = get_job_metadata(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # If completed, include profile data
    if job['status'] == 'COMPLETED' and 'profile_key' in job:
        try:
            profile_response = s3.get_object(Bucket=BUCKET, Key=job['profile_key'])
            profile = json.loads(profile_response['Body'].read())
            job['profile'] = profile
        except Exception as e:
            print(f"Error loading profile: {e}")

    return job


@app.get("/jobs")
async def list_jobs():
    """
    List all jobs from S3
    """
    try:
        # List all job metadata files
        response = s3.list_objects_v2(Bucket=BUCKET, Prefix="jobs/")

        jobs = []
        if 'Contents' in response:
            for obj in response['Contents']:
                if obj['Key'].endswith('metadata.json'):
                    try:
                        job_response = s3.get_object(Bucket=BUCKET, Key=obj['Key'])
                        job = json.loads(job_response['Body'].read())
                        jobs.append(job)
                    except Exception as e:
                        print(f"Error loading job metadata: {e}")

        # Sort by created_at
        jobs.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return {
            "jobs": jobs,
            "total": len(jobs),
            "mode": "s3-only"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat")
async def chat(message: ChatMessage):
    """
    Chat interface (simplified for S3-only mode)
    """
    job_id = message.job_id
    user_message = message.message

    job = get_job_metadata(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job['status'] != 'COMPLETED':
        return {
            "job_id": job_id,
            "user_message": user_message,
            "assistant_response": f"Your file is still processing (status: {job['status']}). Please wait for completion.",
            "status": job['status']
        }

    # Load profile data
    profile = {}
    if 'profile_key' in job:
        try:
            profile_response = s3.get_object(Bucket=BUCKET, Key=job['profile_key'])
            profile = json.loads(profile_response['Body'].read())
        except Exception as e:
            print(f"Error loading profile: {e}")

    # Generate response based on keywords
    response_text = generate_simple_response(user_message, job, profile)

    return {
        "job_id": job_id,
        "user_message": user_message,
        "assistant_response": response_text,
        "is_transformation": False
    }


def generate_simple_response(user_message: str, job: dict, profile: dict) -> str:
    """
    Generate simple chat responses without LLM
    """
    msg_lower = user_message.lower()

    if 'template' in msg_lower:
        templates = job.get('templates', [])
        if templates:
            template_list = '\n'.join([f"- {t['name']} ({len(t['columns'])} columns)" for t in templates])
            return f"I detected {len(templates)} templates in your file:\n\n{template_list}\n\nEach template represents a different data domain."
        else:
            return "No templates were detected in your file yet."

    elif 'convert' in msg_lower or 'transform' in msg_lower:
        return "Transformation features require AWS Bedrock and Glue. To enable full functionality, deploy the complete infrastructure using CloudFormation."

    elif 'status' in msg_lower or 'progress' in msg_lower:
        return f"Your file '{job['filename']}' has been processed successfully!\n\nRows: {profile.get('total_rows', 'N/A')}\nColumns: {profile.get('total_columns', 'N/A')}\nStatus: {job['status']}"

    elif 'columns' in msg_lower or 'data' in msg_lower:
        cols = profile.get('columns', [])
        if cols:
            return f"Your file has {len(cols)} columns:\n{', '.join(cols[:20])}" + ("..." if len(cols) > 20 else "")
        else:
            return "No column information available yet."

    else:
        return f"I've processed your file '{job['filename']}' with {profile.get('total_rows', 'N/A')} rows and {profile.get('total_columns', 'N/A')} columns. What would you like to know about it?"


@app.delete("/job/{job_id}")
async def delete_job(job_id: str):
    """
    Delete job and associated files from S3
    """
    job = get_job_metadata(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    user_id = job['user_id']

    try:
        # Delete all files for this job
        prefix = f"{user_id}/{job_id}/"
        response = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix)

        if 'Contents' in response:
            for obj in response['Contents']:
                s3.delete_object(Bucket=BUCKET, Key=obj['Key'])

        # Delete metadata
        s3.delete_object(Bucket=BUCKET, Key=get_job_metadata_key(job_id))

        return {
            "message": "Job deleted successfully",
            "job_id": job_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/stats")
async def get_stats():
    """
    Get system statistics
    """
    try:
        # Count jobs
        response = s3.list_objects_v2(Bucket=BUCKET, Prefix="jobs/")
        job_count = sum(1 for obj in response.get('Contents', []) if obj['Key'].endswith('metadata.json'))

        return {
            "mode": "s3-only",
            "total_jobs": job_count,
            "s3_bucket": BUCKET,
            "aws_integration": "enabled",
            "note": "Using S3 for storage. For full functionality (Bedrock, Glue), deploy complete infrastructure."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    print("=" * 60)
    print("🚀 Starting Excel Trace Agent (S3-only Production Mode)")
    print("=" * 60)
    print(f"✅ AWS S3 Bucket: {BUCKET}")
    print("✅ Real AWS integration enabled")
    print("✅ Files stored in AWS S3")
    print("✅ Works with limited IAM permissions")
    print("")
    print("⚠️  Note: Full features (Bedrock LLM, Glue transformations)")
    print("   require complete CloudFormation deployment")
    print("=" * 60)
    print("")
    uvicorn.run(app, host="0.0.0.0", port=8000)
