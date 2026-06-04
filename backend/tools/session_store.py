import boto3

ddb = boto3.resource("dynamodb")
table = ddb.Table("job_sessions")


def create_session(job_id, user_id, s3_key):

    table.put_item(Item={
        "job_id": job_id,
        "user_id": user_id,
        "status": "UPLOADED",
        "current_step": "uploaded",
        "s3_input": s3_key
    })


def update_session(job_id, updates):

    expr = "SET " + ", ".join(f"{k}=:{k}" for k in updates.keys())

    table.update_item(
        Key={"job_id": job_id},
        UpdateExpression=expr,
        ExpressionAttributeValues={
            f":{k}": v for k, v in updates.items()
        }
    )


def get_session(job_id):

    res = table.get_item(Key={"job_id": job_id})
    return res.get("Item")