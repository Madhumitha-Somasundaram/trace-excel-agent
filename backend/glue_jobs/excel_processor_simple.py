"""
Simplified Glue job for debugging
"""
import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
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
BUCKET = args['BUCKET']
INPUT_KEY = args['S3_INPUT_KEY']
OUTPUT_PREFIX = args['S3_OUTPUT_PREFIX']
JOB_ID = args['TRACE_JOB_ID']

try:
    print(f"Downloading {BUCKET}/{INPUT_KEY}")
    local_path = f"/tmp/{JOB_ID}.xlsx"
    s3_client.download_file(BUCKET, INPUT_KEY, local_path)

    print("Reading Excel with pandas")
    import pandas as pd
    pdf = pd.read_excel(local_path, engine='openpyxl')

    print(f"Shape: {pdf.shape}")
    print(f"Columns: {list(pdf.columns)}")

    # Sanitize
    pdf.columns = [str(c).strip() for c in pdf.columns]

    print("Converting to Spark DataFrame")
    df = spark.createDataFrame(pdf)

    print(f"Spark DataFrame created. Columns: {df.columns}")
    print(f"Row count: {df.count()}")

    # Simple profile
    profile = {
        'total_rows': df.count(),
        'total_columns': len(df.columns),
        'columns': df.columns
    }

    # Save profile
    profile_key = f"{OUTPUT_PREFIX}/profile.json"
    s3_client.put_object(
        Bucket=BUCKET,
        Key=profile_key,
        Body=json.dumps(profile, indent=2)
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
    cleaned_data_path = f"s3://{BUCKET}/{OUTPUT_PREFIX}/cleaned_data/"
    df.write.mode('overwrite').parquet(cleaned_data_path)

    print("✅ Success!")

except Exception as e:
    print(f"❌ Glue job failed: {str(e)}")
    import traceback
    traceback.print_exc()
    raise e
finally:
    job.commit()
