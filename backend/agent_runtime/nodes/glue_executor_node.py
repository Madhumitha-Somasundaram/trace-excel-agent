"""
Glue Executor Node - Executes user-requested transformations via Glue.
"""
import os

import boto3
import json
import time
from tools.llm import generate_transformation_code
from tools.s3_tool import s3, BUCKET

glue_client = boto3.client('glue', region_name=os.environ.get("AWS_REGION", "us-east-1"))
ddb = boto3.resource('dynamodb', region_name=os.environ.get("AWS_REGION", "us-east-1"))
jobs_table = ddb.Table('jobs')


def glue_executor_node(state):
    """
    Execute user-requested transformations using AWS Glue.

    This node:
    1. Receives user's transformation request from chat
    2. Generates PySpark code using LLM
    3. Creates/runs Glue job with the transformation
    4. Returns transformed data

    Args:
        state: AgentState with user_request for transformation

    Returns:
        Updated state with transformation results
    """

    job_id = state['job_id']
    user_request = state.get('user_request', '')

    if not user_request:
        print("[GlueExecutorNode] No transformation request found, skipping")
        state['next'] = 'finalize'
        return state

    print(f"[GlueExecutorNode] Processing request: {user_request}")

    jobs_table.update_item(
        Key={'job_id': job_id},
        UpdateExpression='SET current_step = :c',
        ExpressionAttributeValues={
            ':c': f'executing_transformation: {user_request[:50]}'
        }
    )

    # Generate transformation code using LLM
    columns = state.get('columns', [])
    sample_data = state.get('sample_data', {})

    transformation = generate_transformation_code(user_request, columns, sample_data)

    if 'error' in transformation:
        state['error'] = f"Failed to generate transformation: {transformation['error']}"
        state['next'] = 'finalize'
        return state

    pyspark_code = transformation.get('code', '')
    explanation = transformation.get('explanation', '')

    print(f"[GlueExecutorNode] Generated transformation: {explanation}")

    # Save transformation code to S3
    user_id = state['s3_key'].split('/')[0]
    transform_script_key = f"{user_id}/{job_id}/transformations/transform_{int(time.time())}.py"

    # Create complete Glue script
    full_script = f"""
# Auto-generated transformation script
# User request: {user_request}
# Explanation: {explanation}

import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from pyspark.sql import SparkSession
from pyspark.sql.functions import *
import boto3

args = getResolvedOptions(sys.argv, ['JOB_NAME', 'INPUT_PATH', 'OUTPUT_PATH'])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session

# Read cleaned data
df = spark.read.parquet(args['INPUT_PATH'])

# User transformation
{pyspark_code}

# Write transformed data
df.write.mode('overwrite').parquet(args['OUTPUT_PATH'], compression='snappy')

print(f"Transformation complete. Rows: {{df.count()}}")
"""

    s3.put_object(
        Bucket=BUCKET,
        Key=transform_script_key,
        Body=full_script,
        ContentType='text/x-python'
    )

    # Run Glue job with transformation
    transform_job_name = 'excel-transformation-job'
    output_path = f"s3://{BUCKET}/{user_id}/{job_id}/transformed/"

    try:
        response = glue_client.start_job_run(
            JobName=transform_job_name,
            Arguments={
                '--INPUT_PATH': state['cleaned_path'],
                '--OUTPUT_PATH': output_path,
                '--extra-py-files': f"s3://{BUCKET}/{transform_script_key}"
            }
        )

        run_id = response['JobRunId']
        print(f"[GlueExecutorNode] Started transformation job: {run_id}")

        # Poll for completion (simplified - in production, use Step Functions)
        max_wait = 10 * 60  # 10 minutes
        wait_interval = 10
        elapsed = 0

        while elapsed < max_wait:
            job_run = glue_client.get_job_run(JobName=transform_job_name, RunId=run_id)
            status = job_run['JobRun']['JobRunState']
            print(f"[GlueExecutorNode] job run : {job_run}")
            print(f"[GlueExecutorNode] status : {status}")
            if status == 'SUCCEEDED':
                state['transformed_path'] = output_path
                state['transformation_explanation'] = explanation
                state['next'] = 'finalize'
                return state

            elif status in ['FAILED', 'TIMEOUT', 'STOPPED']:
                error_msg = job_run['JobRun'].get('ErrorMessage', 'Unknown error')
                state['error'] = f"Transformation failed: {error_msg}"
                state['next'] = 'finalize'
                return state

            time.sleep(wait_interval)
            elapsed += wait_interval

        state['error'] = "Transformation timeout"
        state['next'] = 'finalize'
        return state

    except Exception as e:
        print(f"[GlueExecutorNode] Error: {str(e)}")
        state['error'] = f"Transformation execution error: {str(e)}"
        state['next'] = 'finalize'
        return state