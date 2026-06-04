"""
AWS Glue Job for Excel Processing - Robust version
"""
import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql.functions import col, lit
import boto3
import json

# Initialize
args = getResolvedOptions(sys.argv, ['JOB_NAME', 'S3_INPUT_KEY', 'S3_OUTPUT_PREFIX', 'TRACE_JOB_ID', 'BUCKET'])

sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

s3_client = boto3.client('s3')
ddb = boto3.resource('dynamodb')
table = ddb.Table('jobs')

BUCKET = args['BUCKET']
INPUT_KEY = args['S3_INPUT_KEY']
OUTPUT_PREFIX = args['S3_OUTPUT_PREFIX']
JOB_ID = args['TRACE_JOB_ID']

def update_job_status(status, message, progress):
    """Update DynamoDB with job progress."""
    try:
        table.update_item(
            Key={'job_id': JOB_ID},
            UpdateExpression='SET #s = :s, current_step = :m, progress = :p',
            ExpressionAttributeNames={'#s': 'status'},
            ExpressionAttributeValues={
                ':s': status,
                ':m': message,
                ':p': progress
            }
        )
    except Exception as e:
        print(f"Warning: Failed to update status: {e}")

try:
    print(f"Downloading {BUCKET}/{INPUT_KEY}")
    update_job_status('PROCESSING', 'Downloading Excel from S3...', 10)

    local_path = f"/tmp/{JOB_ID}.xlsx"
    s3_client.download_file(BUCKET, INPUT_KEY, local_path)

    print("Reading Excel with pandas")
    update_job_status('PROCESSING', 'Parsing Excel file...', 20)

    import pandas as pd
    pdf = pd.read_excel(local_path, engine='openpyxl')

    print(f"Shape: {pdf.shape}")
    print(f"Columns: {list(pdf.columns)}")

    # Sanitize column names - CRITICAL
    pdf.columns = [str(c).strip().replace(' ', '_') for c in pdf.columns]

    print("Converting to Spark DataFrame")
    df = spark.createDataFrame(pdf)

    print(f"Spark DataFrame created. Columns: {df.columns}")
    total_rows = df.count()
    print(f"Row count: {total_rows}")

    update_job_status('PROCESSING', 'Profiling data...', 40)

    # Build profile with error handling for each column
    profile = {
        'total_rows': total_rows,
        'total_columns': len(df.columns),
        'columns': {}
    }

    for field in df.schema.fields:
        col_name = str(field.name)  # Ensure it's a string
        col_type = str(field.dataType)

        try:
            # Basic stats with error handling
            null_count = df.filter(col(col_name).isNull()).count()
            null_percentage = (null_count / total_rows * 100) if total_rows > 0 else 0

            # Distinct count
            distinct_count = df.select(col_name).distinct().count()

            col_profile = {
                'data_type': col_type,
                'null_count': int(null_count),
                'null_percentage': round(null_percentage, 2),
                'distinct_count': int(distinct_count),
                'cardinality': 'high' if distinct_count > total_rows * 0.8 else 'medium' if distinct_count > total_rows * 0.3 else 'low'
            }

            # Sample values
            try:
                sample_values = df.select(col_name).filter(col(col_name).isNotNull()).limit(5).rdd.flatMap(lambda x: x).collect()
                col_profile['sample_values'] = [str(v) for v in sample_values]
            except:
                col_profile['sample_values'] = []

            profile['columns'][col_name] = col_profile
            print(f"✓ Profiled column: {col_name}")

        except Exception as e:
            print(f"⚠️  Warning: Could not profile column {col_name}: {e}")
            profile['columns'][col_name] = {
                'data_type': col_type,
                'null_count': 0,
                'null_percentage': 0,
                'distinct_count': 0,
                'cardinality': 'unknown',
                'sample_values': [],
                'error': str(e)
            }

    update_job_status('PROCESSING', 'Saving results...', 70)

    # Save profile
    profile_key = f"{OUTPUT_PREFIX}/profile.json"
    s3_client.put_object(
        Bucket=BUCKET,
        Key=profile_key,
        Body=json.dumps(profile, indent=2, default=str)
    )

    # Save columns
    columns_key = f"{OUTPUT_PREFIX}/columns.json"
    s3_client.put_object(
        Bucket=BUCKET,
        Key=columns_key,
        Body=json.dumps({'columns': df.columns})
    )

    # Sample data
    sample_rows = df.limit(10).toPandas().to_dict('records')
    sample_key = f"{OUTPUT_PREFIX}/sample.json"
    s3_client.put_object(
        Bucket=BUCKET,
        Key=sample_key,
        Body=json.dumps(sample_rows, default=str, indent=2)
    )

    # Write Parquet
    update_job_status('PROCESSING', 'Writing Parquet...', 80)
    cleaned_data_path = f"s3://{BUCKET}/{OUTPUT_PREFIX}/cleaned_data/"
    df.write.mode('overwrite').parquet(cleaned_data_path)

    update_job_status('GLUE_COMPLETE', 'Glue job finished successfully', 90)
    print("✅ Success!")

except Exception as e:
    print(f"❌ Glue job failed: {str(e)}")
    import traceback
    traceback.print_exc()
    update_job_status('FAILED', f"Glue job failed: {str(e)}", 0)
    raise e
finally:
    job.commit()
