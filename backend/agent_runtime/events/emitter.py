import boto3
import os
import time

ddb = boto3.client("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))

def emit(job_id, agent, status, message, progress=None):
    """
    Emit events for real-time updates to DynamoDB.
    """
    try:
        event = {
            "job_id": {"S": job_id},
            "timestamp": {"N": str(int(time.time() * 1000))},  # milliseconds
            "agent": {"S": agent},
            "status": {"S": status},
            "message": {"S": message},
        }

        if progress is not None:
            event["progress"] = {"N": str(progress)}

        ddb.put_item(
            TableName="job_events",
            Item=event
        )
        print(f"[{agent}] {status}: {message} ({progress}%)")
    except Exception as e:
        # Don't fail the job if event logging fails
        print(f"Warning: Failed to emit event: {e}")