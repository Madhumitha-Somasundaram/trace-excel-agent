"""
AWS Glue PySpark Job for Processing Large Excel Files (Millions of Rows, 100+ Columns)

This job handles:
- Reading Excel from S3
- Profiling data (schema, statistics, null counts)
- Caching for performance
- Partitioned writing back to S3
- Scalable processing with optimizations
"""

import sys
from awsglue.transforms import *
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from awsglue.context import GlueContext
from awsglue.job import Job
from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from pyspark.sql.types import *
import boto3
import json

# Initialize Glue context
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
    table.update_item(
        Key={'job_id': JOB_ID},
        UpdateExpression='SET #s = :s, current_step = :m, progress = :p, updated_at = :t',
        ExpressionAttributeNames={'#s': 'status'},
        ExpressionAttributeValues={
            ':s': status,
            ':m': message,
            ':p': progress,
            ':t': str(spark.sparkContext.startTime)
        }
    )


def read_excel_optimized(bucket, key):
    """
    Read Excel file from S3 with optimizations for large files.

    For very large files (>1GB), consider converting to Parquet first.
    """
    update_job_status('PROCESSING', 'Reading Excel from S3...', 10)

    # Download Excel to temp location (Glue has local disk)
    local_path = f"/tmp/{JOB_ID}.xlsx"
    s3_client.download_file(bucket, key, local_path)

    # Read using pandas first for Excel support
    import pandas as pd

    update_job_status('PROCESSING', 'Parsing Excel file...', 20)
    pdf = pd.read_excel(local_path, engine='openpyxl')

    # Sanitize column names to ensure they're all strings
    pdf.columns = [str(c) for c in pdf.columns]

    # Convert to Spark DataFrame for distributed processing
    df = spark.createDataFrame(pdf)

    # Cache for multiple operations
    df.cache()
    df.count()  # Trigger caching

    update_job_status('PROCESSING', f'Loaded {df.count()} rows, {len(df.columns)} columns', 30)

    return df


def profile_dataframe(df):
    """
    Generate comprehensive data profile.

    Returns:
        dict: Profile information including schema, stats, null counts, cardinality
    """
    update_job_status('PROCESSING', 'Profiling data...', 40)

    total_rows = df.count()
    columns = df.columns

    profile = {
        'total_rows': total_rows,
        'total_columns': len(columns),
        'columns': {}
    }

    # Schema information
    for field in df.schema.fields:
        col_name = field.name

        # Ensure col_name is a string
        if not isinstance(col_name, str):
            col_name = str(col_name)

        col_type = str(field.dataType)

        # Compute statistics per column
        null_count = df.filter(col(col_name).isNull()).count()
        null_percentage = (null_count / total_rows * 100) if total_rows > 0 else 0

        # Distinct count (for cardinality)
        distinct_count = df.select(col_name).distinct().count()

        col_profile = {
            'data_type': col_type,
            'null_count': null_count,
            'null_percentage': round(null_percentage, 2),
            'distinct_count': distinct_count,
            'cardinality': 'high' if distinct_count > total_rows * 0.8 else 'medium' if distinct_count > total_rows * 0.3 else 'low'
        }

        # For numeric columns, compute statistics
        if 'int' in col_type.lower() or 'double' in col_type.lower() or 'float' in col_type.lower():
            stats = df.select(
                min(col_name).alias('min'),
                max(col_name).alias('max'),
                avg(col_name).alias('mean'),
                stddev(col_name).alias('stddev')
            ).collect()[0]

            col_profile['statistics'] = {
                'min': stats['min'],
                'max': stats['max'],
                'mean': round(stats['mean'], 2) if stats['mean'] else None,
                'stddev': round(stats['stddev'], 2) if stats['stddev'] else None
            }

        # Sample values
        sample_values = df.select(col_name).filter(col(col_name).isNotNull()).limit(5).rdd.flatMap(lambda x: x).collect()
        col_profile['sample_values'] = [str(v) for v in sample_values]

        profile['columns'][col_name] = col_profile

    return profile


def detect_data_quality_issues(df):
    """
    Identify data quality issues.

    Returns:
        dict: Quality issues found
    """
    update_job_status('PROCESSING', 'Checking data quality...', 50)

    issues = []

    for col_name in df.columns:
        # Check for high null percentage
        null_pct = df.filter(col(col_name).isNull()).count() / df.count() * 100
        if null_pct > 50:
            issues.append({
                'column': col_name,
                'issue': 'high_null_percentage',
                'severity': 'warning',
                'details': f'{null_pct:.1f}% null values'
            })

        # Check for single value (no variance)
        if df.select(col_name).distinct().count() == 1:
            issues.append({
                'column': col_name,
                'issue': 'no_variance',
                'severity': 'info',
                'details': 'Column has only one unique value'
            })

    return {'issues': issues, 'total_issues': len(issues)}


def write_cleaned_data(df, output_path):
    """
    Write processed DataFrame to S3 as Parquet with partitioning.

    Parquet is columnar and highly compressed, ideal for analytics.
    """
    update_job_status('PROCESSING', 'Writing processed data to S3...', 70)

    # Convert to Parquet for efficient storage and future processing
    df.write.mode('overwrite').parquet(output_path, compression='snappy')

    update_job_status('PROCESSING', 'Data written successfully', 80)


def main():
    """Main processing pipeline."""

    try:
        # Step 1: Read Excel
        df = read_excel_optimized(BUCKET, INPUT_KEY)

        # Step 2: Profile data
        profile = profile_dataframe(df)

        # Step 3: Quality checks
        quality = detect_data_quality_issues(df)
        profile['data_quality'] = quality

        # Step 4: Save profile to S3
        profile_key = f"{OUTPUT_PREFIX}/profile.json"
        s3_client.put_object(
            Bucket=BUCKET,
            Key=profile_key,
            Body=json.dumps(profile, indent=2),
            ContentType='application/json'
        )

        # Step 5: Write cleaned data as Parquet
        cleaned_data_path = f"s3://{BUCKET}/{OUTPUT_PREFIX}/cleaned_data/"
        write_cleaned_data(df, cleaned_data_path)

        # Step 6: Save column list for downstream processing
        columns_list = df.columns
        columns_key = f"{OUTPUT_PREFIX}/columns.json"
        s3_client.put_object(
            Bucket=BUCKET,
            Key=columns_key,
            Body=json.dumps({'columns': columns_list}),
            ContentType='application/json'
        )

        # Step 7: Sample data for LLM analysis
        sample_rows = df.limit(10).toPandas().to_dict('records')
        sample_key = f"{OUTPUT_PREFIX}/sample.json"
        s3_client.put_object(
            Bucket=BUCKET,
            Key=sample_key,
            Body=json.dumps(sample_rows, default=str, indent=2),
            ContentType='application/json'
        )

        update_job_status('GLUE_COMPLETE', 'Glue job finished successfully', 90)

        print(f"✅ Processing complete. Profile saved to s3://{BUCKET}/{profile_key}")

    except Exception as e:
        error_msg = f"Glue job failed: {str(e)}"
        print(f"❌ {error_msg}")
        update_job_status('FAILED', error_msg, 0)
        raise e

    finally:
        job.commit()


if __name__ == '__main__':
    main()
