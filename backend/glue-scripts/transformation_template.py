"""
AWS Glue Transformation Template
Owns Glue initialization and executes transformation modules from S3
"""

import sys
import boto3
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job

print("=== AWS Glue Transformation Template ===")

# ✅ FIX: Removed JOB_ID to avoid conflicting option error
args_list = ['JOB_NAME', 'INPUT_PATH', 'OUTPUT_PATH']
args = getResolvedOptions(sys.argv, args_list)

# Extract SCRIPT_KEY manually (optional argument)
script_key = None
for i, arg in enumerate(sys.argv):
    if arg == '--SCRIPT_KEY' and i + 1 < len(sys.argv):
        script_key = sys.argv[i + 1]
        break

# Derive job_id safely (no Glue arg dependency)
job_id = args['INPUT_PATH'].split('/')[1] if '/' in args['INPUT_PATH'] else "UNKNOWN"

print(f"JOB_NAME: {args['JOB_NAME']}")
print(f"INPUT_PATH: {args['INPUT_PATH']}")
print(f"OUTPUT_PATH: {args['OUTPUT_PATH']}")
print(f"JOB_ID (derived): {job_id}")
print(f"SCRIPT_KEY: {script_key}")

# Initialize Glue/Spark contexts (ONCE)
print("\n🔧 Initializing Glue/Spark contexts...")
sc = SparkContext()
glueContext = GlueContext(sc)
spark = glueContext.spark_session
job = Job(glueContext)
job.init(args['JOB_NAME'], args)

print("✅ Glue/Spark contexts initialized")

if not script_key:
    print("\n❌ ERROR: No SCRIPT_KEY provided")
    print("This template requires --SCRIPT_KEY argument")
    job.commit()
    sys.exit(1)

# Determine bucket from INPUT_PATH
bucket = args['INPUT_PATH'].split('/')[2]

print(f"\n📜 Loading transformation module from S3...")
print(f"   Bucket: {bucket}")
print(f"   Key: {script_key}")

try:
    s3 = boto3.client('s3')

    # Download transformation module
    script_obj = s3.get_object(Bucket=bucket, Key=script_key)
    script_content = script_obj['Body'].read().decode('utf-8')

    print(f"   Module size: {len(script_content)} bytes")
    print(f"\n▶️ Executing transformation module...")
    print("=" * 70)

    # Execution namespace
    exec_namespace = {
        '__name__': '__main__',
        '__builtins__': __builtins__,
        'args': args,
        'job_id': job_id,
        'sc': sc,
        'glueContext': glueContext,
        'spark': spark,
        'job': job,
        'boto3': boto3,
        'sys': sys,
    }

    print(f"   Namespace prepared with {len(exec_namespace)} objects")

    # Execute transformation module
    exec(script_content, exec_namespace)

    print("=" * 70)
    print("✅ Transformation module executed successfully")

except Exception as e:
    print(f"\n❌ ERROR loading/executing module: {str(e)}")
    import traceback
    traceback.print_exc()
    raise

finally:
    # Always commit Glue job
    job.commit()
    print("\n✅ Job committed")

print("\n=== Transformation Complete ===")