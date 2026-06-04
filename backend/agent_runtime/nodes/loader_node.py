"""
Loader Node - Triggers AWS Glue job and waits for completion.
"""
import os

import boto3
import time
import json
import os
from tools.s3_tool import s3, BUCKET

REGION = os.environ.get('AWS_REGION', 'us-east-1')
glue_client = boto3.client('glue', region_name=REGION)
ddb = boto3.resource('dynamodb', region_name=REGION)
jobs_table = ddb.Table('jobs')


def loader_node(state):
    """
    Initiates AWS Glue job to process the uploaded Excel file.

    Args:
        state: AgentState containing job_id and s3_key

    Returns:
        Updated state with raw_profile and cleaned_path
    """

    job_id = state['job_id']
    s3_key = state['s3_key']

    print(f"[LoaderNode] Starting Glue job for {job_id}")

    # Update job status
    jobs_table.update_item(
        Key={'job_id': job_id},
        UpdateExpression='SET #s = :s, current_step = :c',
        ExpressionAttributeNames={'#s': 'status'},
        ExpressionAttributeValues={
            ':s': 'PROCESSING',
            ':c': 'starting_glue_job'
        }
    )

    # Define Glue job parameters
    user_id = s3_key.split('/')[0]
    output_prefix = f"{user_id}/{job_id}/processed"

    glue_job_name = 'excel-processor-job'

    try:
        # Start Glue job
        response = glue_client.start_job_run(
            JobName=glue_job_name,
            Arguments={
                '--TRACE_JOB_ID': job_id,
                '--S3_INPUT_KEY': s3_key,
                '--S3_OUTPUT_PREFIX': output_prefix,
                '--BUCKET': BUCKET
            }
        )

        glue_run_id = response['JobRunId']
        print(f"[LoaderNode] Glue job started: {glue_run_id}")

        # Save Glue run ID to DynamoDB
        jobs_table.update_item(
            Key={'job_id': job_id},
            UpdateExpression='SET glue_run_id = :g',
            ExpressionAttributeValues={':g': glue_run_id}
        )

        # Poll for completion (with timeout)
        max_wait = 30 * 60  # 30 minutes max
        wait_interval = 15  # Check every 15 seconds
        elapsed = 0

        while elapsed < max_wait:
            job_run = glue_client.get_job_run(JobName=glue_job_name, RunId=glue_run_id)
            status = job_run['JobRun']['JobRunState']

            print(f"[LoaderNode] Glue job status: {status}")

            if status == 'SUCCEEDED':
                print(f"[LoaderNode] Glue job completed successfully")

                # Load the generated profile from S3
                profile_key = f"{output_prefix}/profile.json"
                profile_obj = s3.get_object(Bucket=BUCKET, Key=profile_key)
                raw_profile = json.loads(profile_obj['Body'].read())

                # Load columns list
                columns_key = f"{output_prefix}/columns.json"
                columns_obj = s3.get_object(Bucket=BUCKET, Key=columns_key)
                columns_data = json.loads(columns_obj['Body'].read())

                # Load sample data
                sample_key = f"{output_prefix}/sample.json"
                sample_obj = s3.get_object(Bucket=BUCKET, Key=sample_key)
                sample_data = json.loads(sample_obj['Body'].read())

                # Update state
                state['raw_profile'] = raw_profile
                state['columns'] = columns_data['columns']
                state['sample_data'] = sample_data
                state['cleaned_path'] = f"s3://{BUCKET}/{output_prefix}/cleaned_data/"
                state['next'] = 'schema_detection'

                jobs_table.update_item(
                    Key={'job_id': job_id},
                    UpdateExpression='SET current_step = :c, progress = :p',
                    ExpressionAttributeValues={
                        ':c': 'glue_completed',
                        ':p': 35
                    }
                )

                return state

            elif status in ['FAILED', 'TIMEOUT', 'STOPPED']:
                error_msg = job_run['JobRun'].get('ErrorMessage', 'Unknown error')
                raise Exception(f"Glue job failed: {error_msg}")

            # Wait before next check
            time.sleep(wait_interval)
            elapsed += wait_interval

        raise Exception("Glue job timeout - exceeded maximum wait time")

    except Exception as e:
        error_msg = f"Loader node error: {str(e)}"
        print(f"[LoaderNode] ERROR: {error_msg}")

        jobs_table.update_item(
            Key={'job_id': job_id},
            UpdateExpression='SET #s = :s, error_message = :e',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':s': 'FAILED',
                ':e': error_msg
            }
        )

        state['error'] = error_msg
        state['next'] = 'END'
        return state
