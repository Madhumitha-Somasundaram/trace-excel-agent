"""
Targeted Transformation Engine - Apply transformations to specific templates only.

This differs from dynamic_transformation_engine.py by:
1. Identifying WHICH templates need modification
2. Fetching ONLY those specific templates
3. Applying transformation to targeted templates
4. Replacing them in the SAME templates/ folder location
"""

import os
import boto3
import json
import time
from typing import Dict, Any, List, Optional
from tools.llm import llm_call

glue_client = boto3.client("glue", region_name=os.environ.get("AWS_REGION", "us-east-1"))
s3_client = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
ddb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
jobs_table = ddb.Table("jobs")

BUCKET = "excel-trace-agent-bucket-549955691461"


def identify_affected_templates(
    user_request: str,
    available_templates: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Determine which specific templates are affected by the user's request.

    Args:
        user_request: User's modification request
        available_templates: List of existing templates with metadata

    Returns:
        Dict with affected template IDs, columns, and confidence
    """

    template_summaries = []
    for tmpl in available_templates:
        template_summaries.append({
            "template_id": tmpl.get("template_id"),
            "template_name": tmpl.get("template_name"),
            "type": tmpl.get("type"),
            "columns": tmpl.get("columns", [])
        })

    prompt = f"""Analyze which templates are affected by this user request.

**User Request:**
"{user_request}"

**Available Templates:**
{json.dumps(template_summaries, indent=2)}

**Your Task:**
Determine EXACTLY which templates need modification based on the request.

Consider:
1. Column names mentioned in the request
2. Template types (transportation, employee, finance, etc.)
3. Semantic understanding (e.g., "distance" relates to transportation template)
4. If request is general ("update all"), mark all templates affected

Return JSON:
{{
  "affected_template_ids": ["template_id1", "template_id2"],
  "reasoning": "why these specific templates are affected",
  "confidence": 0.0-1.0,
  "column_mapping": {{
    "template_id1": ["affected_col1", "affected_col2"],
    "template_id2": ["affected_col3"]
  }},
  "is_global_change": true/false,
  "operation_type": "unit_conversion|aggregation|filtering|enrichment|custom"
}}"""

    return llm_call(prompt, max_tokens=2048, temperature=0.2)


def generate_targeted_pyspark_code(
    user_request: str,
    affected_templates: Dict[str, Any],
    template_schemas: Dict[str, List[str]]
) -> Dict[str, Any]:
    """
    Generate PySpark code that operates on specific templates only.

    Args:
        user_request: User's modification request
        affected_templates: Templates to modify
        template_schemas: Column lists for each template

    Returns:
        PySpark code and metadata
    """

    prompt = f"""Generate PySpark code to transform ONLY the specified templates.

**User Request:**
"{user_request}"

**Templates to Modify:**
{json.dumps(affected_templates, indent=2)}

**Template Schemas:**
{json.dumps(template_schemas, indent=2)}

**Your Task:**
Generate complete PySpark code that:
1. Reads the input DataFrame
2. Applies the transformation ONLY to relevant columns
3. Preserves all other columns unchanged
4. Returns the modified DataFrame

**Code Structure:**
```python
from pyspark.sql import DataFrame
from pyspark.sql.functions import col, when, lit, round as spark_round
from pyspark.sql.types import DoubleType

def transform_data(df: DataFrame) -> DataFrame:
    \"\"\"
    Apply targeted transformation to specific templates.

    User request: {user_request}
    Affected templates: {list(affected_templates.get('affected_template_ids', []))}
    \"\"\"

    # Your transformation logic here
    # Only modify the specific columns identified
    # Keep all other columns as-is

    return df

# Metadata about what changed
RESULT_COLUMNS = []  # columns that were added/modified
AFFECTED_TEMPLATES = []  # template IDs that were changed
```

Return JSON:
{{
  "pyspark_code": "complete Python code as string",
  "explanation": {{
    "what_it_does": "plain English explanation",
    "steps": ["step 1", "step 2"],
    "columns_modified": ["col1", "col2"],
    "templates_affected": ["template_id1"]
  }},
  "input_columns": ["columns read"],
  "output_columns": ["columns in output"],
  "new_columns_created": ["any new columns"],
  "modified_columns": ["existing columns changed"],
  "validation": {{
    "expected_row_count_change": "same|reduced|increased",
    "expected_column_count_change": 0,
    "templates_unchanged": ["template_ids that should NOT change"]
  }}
}}

**IMPORTANT:**
- Use ACTUAL column names from the schemas
- Only modify columns in affected templates
- Do NOT alter unaffected templates' columns
- Preserve data integrity for unchanged data"""

    return llm_call(prompt, max_tokens=6000, temperature=0.1)


def targeted_transformation_executor_node(state):
    """
    Execute transformation on specific templates only.

    Flow:
    1. Identify which templates are affected
    2. Fetch those specific template CSV files
    3. Generate targeted PySpark code
    4. Execute via Glue
    5. Replace ONLY the affected templates in templates/ folder
    """

    job_id = state["job_id"]
    user_request = state.get("user_request", "")

    if not user_request:
        print("[TargetedTransformationExecutor] No transformation request")
        state["next"] = "finalize"
        return state

    print(f"[TargetedTransformationExecutor] Processing: {user_request}")

    jobs_table.update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET current_step = :c, progress = :p",
        ExpressionAttributeValues={
            ":c": "identifying_affected_templates",
            ":p": 50
        }
    )

    # Get existing template files (with s3_key, url, csv_data_key)
    template_files = state.get("template_files", [])
    if not template_files:
        print("[TargetedTransformationExecutor] No existing templates found")
        state["next"] = "finalize"
        return state

    # Step 1: Identify affected templates
    print("[TargetedTransformationExecutor] Step 1: Identifying affected templates...")
    affected_analysis = identify_affected_templates(user_request, template_files)

    # Handle wrapped response from llm_call
    if "response" in affected_analysis and isinstance(affected_analysis["response"], dict):
        affected_analysis = affected_analysis["response"]

    affected_template_ids = affected_analysis.get("affected_template_ids", [])

    if not affected_template_ids:
        print("[TargetedTransformationExecutor] No templates affected - ending")
        state["next"] = "finalize"
        return state

    print(f"[TargetedTransformationExecutor] Affected templates: {affected_template_ids}")

    # Filter to only affected templates
    affected_templates = [
        t for t in template_files
        if t.get("template_id") in affected_template_ids
    ]

    # Build schema mapping
    template_schemas = {
        t["template_id"]: t.get("columns", [])
        for t in affected_templates
    }

    jobs_table.update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET current_step = :c, progress = :p",
        ExpressionAttributeValues={
            ":c": "generating_transformation_code",
            ":p": 60
        }
    )

    # Step 2: Generate targeted PySpark code
    print("[TargetedTransformationExecutor] Step 2: Generating targeted PySpark code...")
    code_result = generate_targeted_pyspark_code(
        user_request,
        affected_analysis,
        template_schemas
    )

    # Handle wrapped response from llm_call
    if "response" in code_result and isinstance(code_result["response"], dict):
        code_result = code_result["response"]

    # Step 3: Create Glue script
    print("[TargetedTransformationExecutor] Step 3: Creating Glue script...")

    pyspark_code = code_result.get('pyspark_code', '')

    # Build transformation MODULE (not a standalone script)
    # The Glue contexts (args, spark, glueContext, job) are passed in by transformation_template.py
    script_part1 = f"""# Targeted Template Transformation Module

from pyspark.sql import DataFrame
from pyspark.sql.functions import *
import pandas as pd
from io import BytesIO

# User-defined transformation function
"""

    script_part2 = f"""

# Transformation execution logic
print(f"Affected templates: {affected_template_ids}")
print(f"Input: {{args['INPUT_PATH']}}")
print(f"Output: {{args['OUTPUT_PATH']}}")

xlsx_path = args['INPUT_PATH']
output_path = args['OUTPUT_PATH']

s3 = boto3.client('s3')
bucket = xlsx_path.split('/')[2]  # Extract bucket from s3://bucket/path

# Process single template
template_id = '{affected_template_ids[0] if affected_template_ids else "UNKNOWN"}'

print(f"\\nProcessing template: {{template_id}}")
print(f"  Input: {{xlsx_path}}")

# Download XLSX from S3
xlsx_key = xlsx_path.replace(f's3://{{bucket}}/', '')
obj = s3.get_object(Bucket=bucket, Key=xlsx_key)
xlsx_data = obj['Body'].read()

# Read XLSX Data sheet into Spark
pandas_df = pd.read_excel(BytesIO(xlsx_data), sheet_name='Data')
df = spark.createDataFrame(pandas_df)

print(f"  Loaded {{df.count()}} rows, {{len(df.columns)}} columns")

# Apply transformation
result_df = transform_data(df)
print(f"  Transformed to {{result_df.count()}} rows, {{len(result_df.columns)}} columns")

# Convert back to Pandas
result_pandas = result_df.toPandas()

# Create new XLSX with Data and Metadata sheets
buffer = BytesIO()
with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
    result_pandas.to_excel(writer, sheet_name='Data', index=False)

    # Keep metadata from original file
    try:
        metadata_df = pd.read_excel(BytesIO(xlsx_data), sheet_name='Metadata')
        # Update row count if it exists
        if 'Property' in metadata_df.columns:
            metadata_df.loc[metadata_df['Property'] == 'Row Count', 'Value'] = len(result_pandas)
            metadata_df.loc[metadata_df['Property'] == 'Column Count', 'Value'] = len(result_pandas.columns)
            metadata_df.loc[metadata_df['Property'] == 'Last Modified', 'Value'] = str(pd.Timestamp.now())
        metadata_df.to_excel(writer, sheet_name='Metadata', index=False)
    except Exception as meta_err:
        print(f"  Creating new metadata (original error: {{meta_err}})")
        # Create new metadata if original doesn't have it
        metadata_rows = [
            {{'Property': 'Template ID', 'Value': template_id}},
            {{'Property': 'Last Modified', 'Value': str(pd.Timestamp.now())}},
            {{'Property': 'Row Count', 'Value': len(result_pandas)}},
            {{'Property': 'Column Count', 'Value': len(result_pandas.columns)}}
        ]
        pd.DataFrame(metadata_rows).to_excel(writer, sheet_name='Metadata', index=False)

buffer.seek(0)

# Upload back to SAME location (replace original)
s3.put_object(
    Bucket=bucket,
    Key=xlsx_key,
    Body=buffer.getvalue(),
    ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
)

print(f"  ✓ Template {{template_id}} updated at {{xlsx_key}}")
print(f"  ✓ Uploaded to s3://{{bucket}}/{{xlsx_key}}")
print("\\n✅ Template transformed successfully")
"""

    full_glue_script = script_part1 + pyspark_code + script_part2

    # Step 4: Upload script
    print("[TargetedTransformationExecutor] Step 4: Uploading Glue script...")

    user_id = state["s3_key"].split("/")[0]
    script_key = f"{user_id}/{job_id}/transformations/targeted_transform_{int(time.time())}.py"

    s3_client.put_object(
        Bucket=BUCKET,
        Key=script_key,
        Body=full_glue_script,
        ContentType="text/x-python"
    )

    # Step 5: Process templates one by one (like dynamic_transformation_engine)
    print(f"[TargetedTransformationExecutor] Step 5: Processing {len(affected_templates)} templates...")

    glue_run_ids = []
    successful_templates = []

    for idx, template in enumerate(affected_templates):
        template_id = template.get("template_id")
        template_name = template.get("template_name")

        print(f"[TargetedTransformationExecutor] Processing {idx+1}/{len(affected_templates)}: {template_name}")

        jobs_table.update_item(
            Key={"job_id": job_id},
            UpdateExpression="SET current_step = :c, progress = :p",
            ExpressionAttributeValues={
                ":c": f"transforming_{template_id}",
                ":p": 70 + (idx * 10 // max(len(affected_templates), 1))
            }
        )

        # Prepare paths
        input_path = f"s3://{BUCKET}/{template['s3_key']}"
        output_path = input_path  # Replace in same location

        try:
            # Pass the script path as an argument
            # The transformation_template.py will load and execute it
            print(f"[TargetedTransformationExecutor] Starting Glue job with script: s3://{BUCKET}/{script_key}")

            response = glue_client.start_job_run(
                JobName="excel-transformation-job",
                Arguments={
                    "--INPUT_PATH": input_path,
                    "--OUTPUT_PATH": output_path,
                    "--JOB_ID": job_id,
                    "--SCRIPT_KEY": script_key
                }
            )

            run_id = response["JobRunId"]
            glue_run_ids.append(run_id)
            print(f"[TargetedTransformationExecutor] Glue job started for {template_id}: {run_id}")

            # Wait for this job to complete before starting next
            wait_start = time.time()
            while time.time() - wait_start < 600:  # 10 min timeout per template
                job_run = glue_client.get_job_run(
                    JobName="excel-transformation-job",
                    RunId=run_id
                )
                status = job_run["JobRun"]["JobRunState"]

                if status == "SUCCEEDED":
                    print(f"[TargetedTransformationExecutor] ✓ {template_name} transformed")
                    successful_templates.append(template_id)
                    break
                elif status in ["FAILED", "TIMEOUT", "STOPPED"]:
                    error_msg = job_run["JobRun"].get("ErrorMessage", "Unknown")
                    print(f"[TargetedTransformationExecutor] ✗ {template_name} failed: {error_msg}")
                    break

                time.sleep(5)

        except Exception as e:
            print(f"[TargetedTransformationExecutor] ERROR {template_id}: {str(e)}")
            continue

    # Store metadata
    state["targeted_transformation_metadata"] = {
        "user_request": user_request,
        "affected_templates": affected_template_ids,
        "successful_templates": successful_templates,
        "affected_analysis": affected_analysis,
        "code_explanation": code_result.get("explanation", {}),
        "glue_run_ids": glue_run_ids,
        "script_location": f"s3://{BUCKET}/{script_key}"
    }

    if len(successful_templates) > 0:
        print(f"[TargetedTransformationExecutor] Transformed {len(successful_templates)}/{len(affected_templates)} templates")
        state["transformation_status"] = "COMPLETED"
        state["next"] = "finalize"
    else:
        state["error"] = "All template transformations failed"
        state["next"] = "finalize"

    return state


def wait_for_targeted_transformation_node(state):
    """
    Wait for targeted transformation to complete, then update affected templates.
    NOTE: This node is not currently used as the executor waits inline for each job.
    Kept for backward compatibility.
    """

    job_id = state["job_id"]

    # Check if we have metadata from executor (jobs already completed)
    metadata = state.get("targeted_transformation_metadata", {})
    if metadata.get("successful_templates"):
        print(f"[TargetedTransformationWaiter] Jobs already completed by executor")
        state["next"] = "finalize"
        return state

    # Legacy path: check for single run_id
    run_id = state.get("glue_run_id")

    if not run_id:
        state["next"] = "finalize"
        return state

    print(f"[TargetedTransformationWaiter] Checking Glue job status: {run_id}")

    # Poll with timeout
    max_wait = 15 * 60  # 15 minutes
    wait_interval = 10
    elapsed = 0

    while elapsed < max_wait:
        try:
            job_run = glue_client.get_job_run(
                JobName="excel-transformation-job",
                RunId=run_id
            )

            status = job_run["JobRun"]["JobRunState"]
            progress = min(70 + (elapsed // wait_interval), 90)

            jobs_table.update_item(
                Key={"job_id": job_id},
                UpdateExpression="SET progress = :p",
                ExpressionAttributeValues={":p": progress}
            )

            print(f"[TargetedTransformationWaiter] Status: {status}")

            if status == "SUCCEEDED":
                print("[TargetedTransformationWaiter] Transformation complete!")

                # XLSX files already updated in place by Glue job
                # Just update metadata in state
                metadata = state.get("targeted_transformation_metadata", {})
                affected_template_ids = metadata.get("affected_templates", [])

                # Update template_files metadata
                template_files = state.get("templates", [])
                for template in template_files:
                    if template.get("template_id") in affected_template_ids:
                        template["last_modified"] = time.strftime('%Y-%m-%d %H:%M:%S')
                        template["transformation_applied"] = state.get("user_request", "")

                        # Regenerate presigned URL for updated XLSX
                        from tools.s3_tool import s3
                        template["url"] = s3.generate_presigned_url(
                            "get_object",
                            Params={"Bucket": BUCKET, "Key": template["s3_key"]},
                            ExpiresIn=3600
                        )

                state["template_files"] = template_files
                state["transformation_status"] = "COMPLETED"

                # Skip regeneration - files already updated
                state["next"] = "finalize"
                return state

            elif status in ["FAILED", "TIMEOUT", "STOPPED"]:
                error_msg = job_run["JobRun"].get("ErrorMessage", "Unknown error")
                print(f"[TargetedTransformationWaiter] FAILED: {error_msg}")

                state["error"] = f"Targeted transformation failed: {error_msg}"
                state["transformation_status"] = "FAILED"
                state["next"] = "finalize"
                return state

            time.sleep(wait_interval)
            elapsed += wait_interval

        except Exception as e:
            print(f"[TargetedTransformationWaiter] Error checking status: {str(e)}")
            time.sleep(wait_interval)
            elapsed += wait_interval

    # Timeout
    state["error"] = "Targeted transformation timeout - exceeded 15 minutes"
    state["transformation_status"] = "TIMEOUT"
    state["next"] = "finalize"

    return state


def generate_updated_template_files_node(state):
    """
    Regenerate Excel files ONLY for the affected templates with updated data.
    Replace them in the same templates/ folder.
    """

    from tools.s3_tool import s3, BUCKET
    import pandas as pd
    from io import BytesIO

    job_id = state["job_id"]
    user_id = state["s3_key"].split("/")[0]
    template_files = state.get("templates", [])
    metadata = state.get("targeted_transformation_metadata", {})
    affected_template_ids = metadata.get("affected_templates", [])

    print(f"[UpdatedTemplateGenerator] Regenerating {len(affected_template_ids)} affected templates")

    jobs_table.update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET current_step = :c, progress = :p",
        ExpressionAttributeValues={
            ":c": "regenerating_affected_templates",
            ":p": 90
        }
    )

    for template in template_files:
        template_id = template.get("template_id")

        # Only regenerate affected templates
        if template_id not in affected_template_ids:
            continue

        print(f"[UpdatedTemplateGenerator] Regenerating: {template['template_name']}")

        # Read updated CSV data
        csv_key = template.get("csv_data_key")

        try:
            # Handle Glue output (might be in _temp folder with part files)
            if "_temp" in csv_key:
                # List files in the temp folder
                prefix = csv_key.replace(f"s3://{BUCKET}/", "")
                response = s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix)

                csv_files = [
                    obj["Key"] for obj in response.get("Contents", [])
                    if obj["Key"].endswith(".csv") and "part-" in obj["Key"]
                ]

                if csv_files:
                    csv_key = csv_files[0]  # Take first part file

            obj = s3.get_object(Bucket=BUCKET, Key=csv_key.replace(f"s3://{BUCKET}/", ""))
            df = pd.read_csv(BytesIO(obj["Body"].read()))

            print(f"[UpdatedTemplateGenerator] Loaded {len(df)} rows, {len(df.columns)} columns")

            # Generate new Excel file
            buffer = BytesIO()

            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                df.to_excel(writer, sheet_name="Data", index=False)

                # Update metadata sheet
                metadata_rows = [
                    {"Property": "Template ID", "Value": template_id},
                    {"Property": "Template Name", "Value": template["template_name"]},
                    {"Property": "Template Type", "Value": template["type"]},
                    {"Property": "Last Modified", "Value": template.get("last_modified", "")},
                    {"Property": "Transformation", "Value": template.get("transformation_applied", "")},
                    {"Property": "Row Count", "Value": len(df)},
                    {"Property": "Column Count", "Value": len(df.columns)}
                ]

                metadata_df = pd.DataFrame(metadata_rows)
                metadata_df.to_excel(writer, sheet_name="Metadata", index=False)

            buffer.seek(0)

            # Upload to SAME location (replace existing)
            s3_key = template["s3_key"]

            s3.put_object(
                Bucket=BUCKET,
                Key=s3_key,
                Body=buffer.getvalue(),
                ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            # Update download URL
            download_url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": BUCKET, "Key": s3_key},
                ExpiresIn=3600
            )

            template["url"] = download_url
            template["row_count"] = len(df)
            template["columns"] = list(df.columns)

            print(f"[UpdatedTemplateGenerator] Updated: {template['template_name']} at {s3_key}")

        except Exception as e:
            print(f"[UpdatedTemplateGenerator] Error updating {template_id}: {e}")
            import traceback
            traceback.print_exc()

    state["template_files"] = template_files
    state["next"] = "finalize"

    print(f"[UpdatedTemplateGenerator] Successfully updated {len(affected_template_ids)} templates")

    return state
