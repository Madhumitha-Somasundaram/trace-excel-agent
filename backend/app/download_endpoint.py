"""
Template Download Endpoint - Returns downloadable template files
"""
from fastapi import HTTPException
import boto3
from typing import List, Dict

s3 = boto3.client('s3')
ddb = boto3.resource('dynamodb')
table = ddb.Table('jobs')

BUCKET = "excel-trace-agent-bucket-549955691461"


def get_template_downloads(job_id: str) -> List[Dict]:
    """
    Generate download links for template files.
    
    Returns list of templates with download URLs.
    """
    try:
        # Get job info
        response = table.get_item(Key={"job_id": job_id})

        if 'Item' not in response:
            raise HTTPException(status_code=404, detail="Job not found")

        job = response['Item']
        user_id = job['user_id']

        # List template files in S3
        prefix = f"{user_id}/{job_id}/templates/"

        response = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix)

        if 'Contents' not in response:
            return []

        template_files = []

        for obj in response['Contents']:
            key = obj['Key']

            # Skip metadata.json
            if key.endswith('.json'):
                continue

            # Only process .xlsx files
            if not key.endswith('.xlsx'):
                continue

            # Extract template name from filename
            filename = key.split('/')[-1]
            template_name = filename.replace('.xlsx', '').replace('_', ' ')

            # Generate pre-signed URL (24 hours)
            url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': BUCKET, 'Key': key},
                ExpiresIn=86400
            )

            # Get file size
            file_size = obj['Size']

            template_files.append({
                'name': filename,
                'template_name': template_name,
                'url': url,
                's3_key': key,
                'size': file_size,
                'size_mb': round(file_size / (1024 * 1024), 2)
            })

        return template_files

    except Exception as e:
        print(f"Error getting template downloads: {e}")
        return []
