"""
Dynamic Transformation Engine - Fully LLM-driven transformations.

NO static rules. Everything is analyzed from:
1. User's natural language request
2. Actual dataset schema and statistics
3. Sample data patterns
4. Detected templates and relationships

The LLM generates complete PySpark code tailored to the specific dataset.
"""

import os
import boto3
import json
import time
from typing import Dict, Any, List, Optional
from tools.llm import llm_call
from agent_runtime.conversation_memory import ConversationMemory

glue_client = boto3.client(
    "glue", region_name=os.environ.get("AWS_REGION", "us-east-1")
)
s3_client = boto3.client("s3", region_name=os.environ.get("AWS_REGION", "us-east-1"))
ddb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
jobs_table = ddb.Table("jobs")

BUCKET = "excel-trace-agent-bucket-549955691461"


def analyze_user_intent(
    user_request: str, available_context: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Deeply analyze what the user wants to do with their data.

    Returns:
        - Intent classification
        - Required columns
        - Expected output
        - Complexity assessment
    """

    prompt = f"""Analyze this user request in the context of their dataset.

**User Request:**
"{user_request}"

**Available Context:**
- Templates: {json.dumps(available_context.get('template_names', []))}
- Column count: {available_context.get('total_columns', 0)}
- Row count: {available_context.get('total_rows', 0)}
- Sample columns: {json.dumps(available_context.get('sample_columns', [])[:20])}

**Your Task:**
Understand EXACTLY what the user wants:

1. **Intent Type:** Is this:
   - Unit conversion (change measurement units)
   - Aggregation (group and calculate)
   - Filtering (select subset)
   - Joining (combine data)
   - Enrichment (add calculated columns)
   - Cleaning (fix data quality)
   - Reshaping (pivot, unpivot, etc)
   - Statistical analysis
   - Custom complex operation

2. **Required Data:** Which columns/data are needed?

3. **Expected Output:** What should the result look like?

4. **Ambiguities:** Is anything unclear that needs clarification?

Return JSON:
{{
  "intent_type": "conversion|aggregation|filtering|joining|enrichment|cleaning|reshaping|statistical|custom",
  "confidence": 0.0-1.0,
  "required_columns": ["list of column names needed"],
  "column_inference": {{
    "explicit": ["columns explicitly mentioned"],
    "inferred": ["columns we think they mean"],
    "ambiguous": ["columns that might be relevant but unclear"]
  }},
  "operation_details": {{
    "primary_operation": "main thing to do",
    "secondary_operations": ["supporting operations"],
    "parameters": {{"any_params": "needed"}}
  }},
  "expected_output": {{
    "output_type": "new_column|new_dataset|aggregated_table|filtered_data",
    "description": "what the output should contain"
  }},
  "complexity": "simple|moderate|complex",
  "needs_clarification": true/false,
  "clarification_questions": ["questions to ask user if unclear"],
  "similar_examples": ["example queries that would produce similar results"]
}}"""

    return llm_call(prompt, max_tokens=2048, temperature=0.2)


def generate_pyspark_code_from_analysis(
    intent_analysis: Dict[str, Any],
    full_schema: Dict[str, Any],
    sample_data: List[Dict],
    templates: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Generate complete, production-ready PySpark code based on analysis.

    This is where the magic happens - NO hardcoded patterns.
    """

    # Prepare comprehensive context
    column_details = {}
    for col_name, col_info in full_schema.get("columns", {}).items():
        column_details[col_name] = {
            "type": col_info.get("data_type"),
            "nulls": col_info.get("null_percentage"),
            "cardinality": col_info.get("cardinality"),
            "stats": col_info.get("statistics", {}),
            "samples": col_info.get("sample_values", [])[:5],
        }
    # Handle templates as either list or dict
    print(f'[d_tranform 1st] in {templates}')
    if isinstance(templates, list):
        template_names = [t.get('template_name', t.get('template_type', 'unknown')) for t in templates]
    elif isinstance(templates, dict):
        template_names = [v.get('template_name', v.get('template_type', 'unknown')) for v in templates.values()]
    else:
        template_names = []
    print(f'[d_tranform] {template_names}')
    prompt = f"""Generate PySpark code for this data transformation.

**User Request:**
"{intent_analysis.get('intent_type', 'transformation')}: {intent_analysis.get('operation_details', {}).get('primary_operation', 'data processing')}"

**Available Columns:**
{json.dumps(list(column_details.keys())[:30], indent=2)}

**Sample Data (first 2 rows):**
{json.dumps(sample_data[:2], indent=2, default=str)}

**Detected Templates:**
{json.dumps(template_names, indent=2)}

**Your Task:**
Generate complete PySpark code that:
1. Reads the input DataFrame
2. Applies the requested transformation
3. Returns the modified DataFrame

**REQUIRED Code Structure:**
```python
from pyspark.sql import DataFrame
from pyspark.sql.functions import col, when, lit  # Only import what you need

def transform_data(df: DataFrame) -> DataFrame:
    \"\"\"
    Brief description of what this does.
    \"\"\"

    # Your transformation logic here
    # Use actual column names from schema
    # Handle nulls and edge cases

    return df
```

**CRITICAL REQUIREMENTS:**
- MUST have exactly: `def transform_data(df: DataFrame) -> DataFrame:`
- The function MUST return a DataFrame (not dict, not tuple, not None)
- NO classes, NO helper methods, NO complex patterns
- NO emojis or Unicode characters (use only ASCII)
- Keep code under 150 lines total
- Code must compile without syntax errors

**Code Structure (repeat for clarity):**
```python
from pyspark.sql import DataFrame
from pyspark.sql.functions import col, when, lit, [other_needed_functions]

def transform_data(df: DataFrame) -> DataFrame:
    \"\"\"
    [Description of what this transformation does]

    Args:
        df: Input DataFrame with columns: [list columns]

    Returns:
        Transformed DataFrame with [describe output]
    \"\"\"

    # [Your implementation here]
    # Use best practices for PySpark
    # Handle nulls appropriately
    # Add error handling if needed

    return df

# Result columns that will be produced
RESULT_COLUMNS = ["list", "of", "output", "columns"]
```

Return JSON:
{{
  "pyspark_code": "complete Python code as string",
  "explanation": {{
    "what_it_does": "plain English explanation",
    "steps": ["step 1", "step 2"],
    "columns_modified": ["col1", "col2"]
  }},
  "input_columns": ["columns read"],
  "output_columns": ["columns in output"],
  "new_columns_created": ["any new columns"],
  "modified_columns": ["existing columns changed"],
  "transformations_applied": ["list of transformations"],
  "validation": {{
    "expected_row_count_change": "same|reduced|increased",
    "expected_column_count_change": 0
  }}
}}

**IMPORTANT:**
- Use ACTUAL column names from the schema
- Code must be syntactically valid Python
- The transform_data function must return a DataFrame
- Keep it simple and direct"""

    return llm_call(prompt, max_tokens=6000, temperature=0.1)


def validate_generated_code(
    code_result: Dict[str, Any], available_columns: List[str]
) -> Dict[str, Any]:
    """
    Validate that generated code is safe and references real columns.
    """

    pyspark_code = code_result.get("pyspark_code", "")
    input_columns = code_result.get("input_columns", [])

    validation_result = {"is_valid": True, "errors": [], "warnings": []}

    # Check for missing columns
    missing_columns = [col for col in input_columns if col not in available_columns]
    if missing_columns:
        validation_result["is_valid"] = False
        validation_result["errors"].append(
            f"Columns not found in dataset: {missing_columns}"
        )

    # Check for dangerous operations
    dangerous_patterns = [
        "DROP TABLE",
        "DELETE",
        "TRUNCATE",
        "__import__",
        "exec(",
        "eval(",
    ]
    for pattern in dangerous_patterns:
        if pattern in pyspark_code.upper():
            validation_result["is_valid"] = False
            validation_result["errors"].append(
                f"Dangerous operation detected: {pattern}"
            )

    # Check for syntax (basic)
    try:
        compile(pyspark_code, "<string>", "exec")
    except SyntaxError as e:
        validation_result["is_valid"] = False
        # Show the problematic line
        lines = pyspark_code.split('\n')
        error_line = e.lineno if e.lineno and e.lineno <= len(lines) else 1
        context_start = max(0, error_line - 3)
        context_end = min(len(lines), error_line + 2)
        error_context = '\n'.join(f"{i+1}: {lines[i]}" for i in range(context_start, context_end))
        validation_result["errors"].append(
            f"Syntax error at line {e.lineno}: {str(e)}\nContext:\n{error_context}"
        )

    return validation_result


def dynamic_transformation_executor_node(state):
    """
    Fully dynamic transformation execution.

    Flow:
    1. Analyze user intent deeply
    2. Generate PySpark code from scratch
    3. Validate code
    4. Execute via Glue
    5. Return results
    """

    job_id = state["job_id"]
    user_request = state.get("user_request", "")

    if not user_request:
        print("[DynamicTransformationExecutor] No transformation request")
        state["next"] = "finalize"
        return state

    print(f"[DynamicTransformationExecutor] Processing: {user_request}")

    jobs_table.update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET current_step = :c",
        ExpressionAttributeValues={
            ":c": f"analyzing_transformation: {user_request[:50]}"
        },
    )

    # Initialize conversation memory
    user_id = state['s3_key'].split('/')[0]
    conversation = ConversationMemory(job_id, user_id)

    # Add user message to history
    conversation.add_message('user', user_request)

    # Check for pending clarifications
    pending_clarification = conversation.get_pending_clarification()
    if pending_clarification:
        user_lower = user_request.lower().strip()
        if any(kw in user_lower for kw in ['yes', 'proceed', 'go ahead', 'continue', 'ok']):
            print("[DynamicTransformationExecutor] User confirmed - proceeding")
            conversation.mark_clarification_answered()
            # Skip clarification check - proceed with transformation
        elif any(kw in user_lower for kw in ['no', 'cancel', 'stop']):
            conversation.add_message('assistant', "Transformation cancelled.")
            state['next'] = 'finalize'
            return state

    # Prepare context for analysis
    templates = state.get('templates', {})
    templates_list = templates.values() if isinstance(templates, dict) else templates

    available_context = {
        'template_names': [t.get('template_name') for t in templates_list],
        'total_columns': len(state.get('columns', [])),
        'total_rows': state.get('raw_profile', {}).get('total_rows', 0),
        'sample_columns': state.get('columns', [])
    }

    # Step 1: Analyze user intent
    print("[DynamicTransformationExecutor] Step 1: Analyzing intent...")
    intent_analysis = analyze_user_intent(user_request, available_context)

    # Only ask for clarification if confidence is low
    if intent_analysis.get('needs_clarification') and intent_analysis.get('confidence', 1.0) < 0.75:
        clarification_msg = "I need clarification:\n\n"
        questions = intent_analysis.get('clarification_questions', [])[:3]
        for i, q in enumerate(questions, 1):
            clarification_msg += f"{i}. {q}\n"
        clarification_msg += "\nSay 'proceed' to continue anyway."

        conversation.add_message('assistant', clarification_msg, {
            'type': 'clarification',
            'clarification_context': {
                'questions': questions,
                'original_request': user_request,
                'intent_analysis': intent_analysis
            }
        })

        state['clarification_needed'] = True
        state['clarification_message'] = clarification_msg
        state['clarification_questions'] = questions
        state['next'] = 'finalize'
        return state

    # Step 2: Generate PySpark code
    print("[DynamicTransformationExecutor] Step 2: Generating PySpark code...")
    code_result = generate_pyspark_code_from_analysis(
        intent_analysis,
        state.get("raw_profile", {}),
        state.get("sample_data", []),
        state.get("templates", {}),
    )

    # Step 3: Validate code
    print("[DynamicTransformationExecutor] Step 3: Validating code...")
    validation = validate_generated_code(code_result, state.get("columns", []))

    if not validation["is_valid"]:
        error_msg = f"Code validation failed: {', '.join(validation['errors'])}"
        print(f"[DynamicTransformationExecutor] ERROR: {error_msg}")
        state["error"] = error_msg
        state["next"] = "finalize"
        return state

    # Step 4: Create complete Glue script
    print("[DynamicTransformationExecutor] Step 4: Creating Glue script...")

    # Extract PySpark code - it should be at module level, not indented
    pyspark_code = code_result.get('pyspark_code', '')

    # Build transformation MODULE (not a standalone script)
    # The Glue contexts (args, spark, glueContext, job) are passed in by transformation_template.py
    script_part1 = f"""# Dynamic Transformation Module
from pyspark.sql import DataFrame
from pyspark.sql.functions import *

# User-defined transformation function (at module level)
"""

    # Add the transformation code at module level (no extra indentation)
    # It should already be properly formatted

    # Execution logic (module level, no try/finally/job.commit)
    script_part2 = f"""

# Transformation execution logic
print(f"Input: {{args['INPUT_PATH']}}")
print(f"Output: {{args['OUTPUT_PATH']}}")

# Read input data
df = spark.read.parquet(args['INPUT_PATH'])
print(f"Loaded {{df.count()}} rows, {{len(df.columns)}} columns")

# Apply transformation
result_df = transform_data(df)

print(f"Transformation complete: {{result_df.count()}} rows, {{len(result_df.columns)}} columns")

# Write output
result_df.write.mode('overwrite').parquet(args['OUTPUT_PATH'], compression='snappy')

print("Output written successfully")

"""

    # Combine all parts - pyspark_code goes at module level (no indentation needed)
    full_glue_script = script_part1 + pyspark_code + script_part2

    # Step 5: Upload script and execute Glue job
    print("[DynamicTransformationExecutor] Step 5: Executing Glue job...")

    user_id = state["s3_key"].split("/")[0]
    script_key = f"{user_id}/{job_id}/transformations/transform_{int(time.time())}.py"

    s3_client.put_object(
        Bucket=BUCKET,
        Key=script_key,
        Body=full_glue_script,
        ContentType="text/x-python",
    )

    # Execute Glue job
    output_path = f"s3://{BUCKET}/{user_id}/{job_id}/transformed/"

    try:
        response = glue_client.start_job_run(
            JobName="excel-transformation-job",
            Arguments={
                "--INPUT_PATH": state.get("cleaned_path", ""),
                "--OUTPUT_PATH": output_path,
                "--JOB_ID": job_id,
                "--SCRIPT_KEY": script_key,
            },
        )

        run_id = response["JobRunId"]
        print(f"[DynamicTransformationExecutor] Glue job started: {run_id}")

        # Store execution metadata
        state["transformation_metadata"] = {
            "user_request": user_request,
            "intent_analysis": intent_analysis,
            "code_explanation": code_result.get("explanation", {}),
            "glue_run_id": run_id,
            "script_location": f"s3://{BUCKET}/{script_key}",
            "output_location": output_path,
            "estimated_time": code_result.get("estimated_execution_time", "unknown"),
            "input_columns": code_result.get("input_columns", []),
            "output_columns": code_result.get("output_columns", []),
            "new_columns": code_result.get("new_columns_created", []),
        }

        state["glue_run_id"] = run_id
        state["transformed_path"] = output_path
        state["next"] = "wait_for_transformation"

        return state

    except Exception as e:
        error_msg = f"Failed to execute Glue job: {str(e)}"
        print(f"[DynamicTransformationExecutor] ERROR: {error_msg}")
        state["error"] = error_msg
        state["next"] = "finalize"
        return state


def wait_for_transformation_node(state):
    """
    Wait for Glue transformation to complete (async polling).
    """

    job_id = state["job_id"]
    run_id = state.get("glue_run_id")

    if not run_id:
        state["next"] = "finalize"
        return state

    print(f"[TransformationWaiter] Checking Glue job status: {run_id}")

    # Poll with timeout
    max_wait = 20 * 60  # 20 minutes
    wait_interval = 15
    elapsed = 0

    while elapsed < max_wait:
        try:
            job_run = glue_client.get_job_run(
                JobName="excel-transformation-job", RunId=run_id
            )

            status = job_run["JobRun"]["JobRunState"]
            print(f"[TransformationWaiter] Status: {status}")

            if status == "SUCCEEDED":
                print("[TransformationWaiter] Transformation complete!")

                state["transformation_status"] = "COMPLETED"
                state["next"] = "generate_template_files"
                return state

            elif status in ["FAILED", "TIMEOUT", "STOPPED"]:
                error_msg = job_run["JobRun"].get("ErrorMessage", "Unknown error")
                print(f"[TransformationWaiter] FAILED: {error_msg}")

                state["error"] = f"Transformation failed: {error_msg}"
                state["transformation_status"] = "FAILED"
                state["next"] = "finalize"
                return state

            time.sleep(wait_interval)
            elapsed += wait_interval

        except Exception as e:
            print(f"[TransformationWaiter] Error checking status: {str(e)}")
            time.sleep(wait_interval)
            elapsed += wait_interval

    # Timeout
    state["error"] = "Transformation timeout - exceeded 20 minutes"
    state["transformation_status"] = "TIMEOUT"
    state["next"] = "finalize"

    return state