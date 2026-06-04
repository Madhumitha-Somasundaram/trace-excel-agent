import boto3
from io import BytesIO
import pandas as pd
import os

s3 = boto3.client("s3")
BUCKET = os.environ.get("BUCKET_NAME", "excel-trace-agent-bucket-549955691461")


def read_excel(key):
    obj = s3.get_object(Bucket=BUCKET, Key=key)
    return pd.read_excel(BytesIO(obj["Body"].read()))