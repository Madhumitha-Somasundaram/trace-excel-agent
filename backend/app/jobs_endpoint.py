from fastapi import APIRouter, Depends, HTTPException
from models.user import User
from auth.dependencies import get_current_user
import boto3

router = APIRouter()

ddb = boto3.resource("dynamodb", region_name="us-east-1")
table = ddb.Table("jobs")


@router.get("/jobs")
async def get_user_jobs(
    current_user: User = Depends(get_current_user),
    limit: int = 20
):
    """Get all jobs for authenticated user"""
    try:
        response = table.scan(
            FilterExpression="user_id = :user_id",
            ExpressionAttributeValues={":user_id": current_user.username},
            Limit=limit
        )

        jobs = response.get('Items', [])
        jobs.sort(key=lambda x: x.get('created_at', ''), reverse=True)

        return {
            "jobs": jobs,
            "count": len(jobs)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
