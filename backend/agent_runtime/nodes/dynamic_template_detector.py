"""
Dynamic Template Detector - Discovers multiple templates within a single Excel file.

This analyzes column semantics, data patterns, and relationships to identify
distinct data domains/templates that may exist in the same file.

Example: A file with vehicle columns + employee columns would detect both
Transportation AND Employee templates.

Uses AWS Bedrock for AI capabilities instead of local models.
"""

import os

import os
import boto3
import json
from typing import Dict, Any, List, Tuple
from tools.llm import llm_call

ddb = boto3.resource("dynamodb", region_name=os.environ.get("AWS_REGION", "us-east-1"))
jobs_table = ddb.Table("jobs")

import json
import re

def extract_json(text):
    if not text:
        return {}

    # remove code fences
    text = text.strip()
    text = re.sub(r"```json", "", text)
    text = re.sub(r"```", "", text)

    # remove any log lines accidentally injected
    text = "\n".join(
        line for line in text.splitlines()
        if not line.startswith("Jun ") and "ip-" not in line
    )

    # extract first JSON object
    match = re.search(r"\{.*\}", text, re.DOTALL)
    print(match,json.loads(match.group(0)))
    if not match:
        return {}

    try:
        return json.loads(match.group(0))
    except Exception:
        return {}

def analyze_column_relationships(
    columns: List[str], sample_data: List[Dict]
) -> Dict[str, Any]:
    """
    Analyze relationships between columns to understand data structure.

    Returns:
        - Potential foreign key relationships
        - Hierarchies (parent-child)
        - Co-occurrence patterns
        - Semantic groupings
    """

    prompt = f"""Analyze these columns and sample data to understand relationships and structure.

Columns: {json.dumps(columns)}

Sample data (first 5 rows):
{json.dumps(sample_data[:5], indent=2, default=str)}

Identify:
1. Which columns are identifiers (IDs, keys)?
2. Which columns likely belong together (same entity/domain)?
3. Are there multiple distinct entities/domains in this dataset?
4. What are the relationships between column groups?

Return JSON:
{{
  "identifiers": ["list of ID columns"],
  "column_groups": [
    {{
      "group_name": "descriptive name",
      "columns": ["col1", "col2"],
      "entity_type": "what this represents",
      "reasoning": "why these belong together"
    }}
  ],
  "relationships": [
    {{
      "from_group": "group1",
      "to_group": "group2",
      "relationship_type": "one-to-many|many-to-many|hierarchical",
      "explanation": "how they relate"
    }}
  ],
  "distinct_domains": ["transportation", "employee", "finance", etc]
}}"""

    return llm_call(prompt, max_tokens=2048, temperature=0.3)


def detect_templates_from_analysis(
    columns: List[str], sample_data: List[Dict], profile: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Use LLM to detect ALL templates present in the data.

    This is the core dynamic detection - no static rules.
    """

    # Prepare data context for LLM
    column_stats = {}
    for col_name, col_info in profile.get("columns", {}).items():
        column_stats[col_name] = {
            "data_type": col_info.get("data_type"),
            "null_percentage": col_info.get("null_percentage"),
            "cardinality": col_info.get("cardinality"),
            "sample_values": col_info.get("sample_values", [])[:3],
        }

    prompt = f"""You are a data analysis expert. Analyze this dataset to identify ALL distinct templates/domains present.

**Dataset Overview:**
Total columns: {len(columns)}
Total rows: {profile.get('total_rows', 0)}

**Column Statistics:**
{json.dumps(column_stats, indent=2)}

**Sample Data (first 3 rows):**
{json.dumps(sample_data[:3], indent=2, default=str)}

**Your Task:**
Identify EVERY distinct template/data domain in this dataset. A template is a coherent group of columns representing a specific business entity or process.

Common templates include (but not limited to):
- Transportation/Logistics: vehicle, route, distance, fuel, delivery
- Employee/HR: employee_id, name, department, salary, hire_date
- Finance/Accounting: transaction, amount, account, date, category
- Inventory: product, sku, quantity, warehouse, supplier
- Sales: order, customer, product, price, revenue
- Manufacturing: batch, machine, production, quality
- Healthcare: patient, diagnosis, treatment, medication
- Education: student, course, grade, enrollment

**IMPORTANT:**
1. A SINGLE file can contain MULTIPLE templates (e.g., employee data + department data + payroll data)
2. Look for semantic clustering - columns that naturally go together
3. Consider data relationships and hierarchies
4. Identify the primary purpose of each template

Return JSON:
{{
  "templates": [
    {{
      "template_id": "unique_id",
      "template_name": "Transportation Data",
      "template_type": "transportation|employee|finance|inventory|sales|manufacturing|healthcare|education|custom",
      "confidence": 0.0-1.0,
      "columns": ["list of columns in this template"],
      "primary_identifier": "main ID column",
      "description": "what this template represents",
      "key_metrics": ["important numeric/calculated columns"],
      "temporal_columns": ["date/time columns if any"],
      "categorical_columns": ["categorical columns for grouping"],
      "business_domain": "specific domain name",
      "typical_use_cases": ["list of common analyses for this template"],
      "relationships_to_other_templates": ["how this connects to other templates in the file"]
    }}
  ],
  "overall_analysis": {{
    "primary_purpose": "main purpose of this dataset",
    "data_complexity": "simple|moderate|complex",
    "recommended_analyses": ["suggestions for the user"],
    "data_quality_summary": "brief quality assessment"
  }}
}}

Be thorough - find ALL templates, even if they're small or secondary."""

    return llm_call(prompt, max_tokens=4096, temperature=0.2)


def enrich_template_with_ml_clustering(
    template: Dict[str, Any],
    all_columns: List[str],
    embeddings_cache: Dict[str, list] = None,
) -> Dict[str, Any]:
    """
    Placeholder for template enrichment (simplified for Bedrock-only deployment).
    """
    # Simplified version without embeddings
    return template

    template_columns = template["columns"]

    # Get embeddings for these columns
    if not embeddings_cache:
        all_embeddings = model.encode(all_columns)
        embeddings_cache.update(
            {col: emb for col, emb in zip(all_columns, all_embeddings)}
        )

    template_embeddings = np.array([embeddings_cache[col] for col in template_columns])

    # Calculate cohesion score (how similar columns are within template)
    if len(template_embeddings) > 1:
        from sklearn.metrics.pairwise import cosine_similarity

        similarities = cosine_similarity(template_embeddings)
        cohesion_score = np.mean(similarities[np.triu_indices_from(similarities, k=1)])
    else:
        cohesion_score = 1.0

    template["ml_cohesion_score"] = float(cohesion_score)
    template["ml_verified"] = cohesion_score > 0.6

    return template


def dynamic_template_detection_node(state):
    """
    Enhanced template detection that finds multiple templates dynamically.

    This replaces the static template detection with full LLM analysis.
    """

    job_id = state["job_id"]
    columns = state["columns"]
    sample_data = state["sample_data"]
    profile = state["raw_profile"]

    print(
        f"[DynamicTemplateDetector] Analyzing {len(columns)} columns for multiple templates"
    )

    jobs_table.update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET current_step = :c, progress = :p",
        ExpressionAttributeValues={":c": "dynamic_template_detection", ":p": 55},
    )

    # Step 1: Analyze column relationships
    print("[DynamicTemplateDetector] Step 1: Analyzing column relationships...")
    relationship_analysis = analyze_column_relationships(columns, sample_data)
    
    print("[DynamicTemplateDetector] Step 2: Detecting templates with LLM...")

    template_detection = detect_templates_from_analysis(columns, sample_data, profile)

    if not template_detection or 'error' in template_detection:
        print(f"[DynamicTemplateDetector] Error: {template_detection.get('error', 'Unknown error')}")
        state['templates'] = {}
        state['next'] = 'finalize'
        return state


    def extract_templates(obj):
        """Single source of truth for parsing templates"""
    
        if isinstance(obj, dict):
            if "templates" in obj and isinstance(obj["templates"], list):
                return obj["templates"]

        if isinstance(obj, str):
            import json
            import re

            text = obj.strip()

            # remove markdown
            text = text.replace("```json", "").replace("```", "")

            # extract JSON safely
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if not match:
                return []

            try:
                parsed = json.loads(match.group(0))
                return parsed.get("templates", [])
            except Exception:
                return []

        return []


    # SINGLE SOURCE OF TRUTH
    templates_list = extract_templates(template_detection)

    print(f"[DynamicTemplateDetector] Extracted {len(templates_list)} templates from LLM response")

    print(f"[DEBUG] template_detection keys: {list(template_detection.keys())}")
    print(f"[DEBUG] templates value: {template_detection.get('templates', 'KEY NOT FOUND')}")


    # Fallback ONLY if truly empty
    if not templates_list:
        print("[DynamicTemplateDetector] No templates detected - using fallback")

        templates_list = []
        for group in relationship_analysis.get('response', {}).get('column_groups', []):
            templates_list.append({
            'template_id': group['entity_type'].lower().replace(' ', '_'),
            'template_name': group['group_name'],
            'template_type': 'custom',
            'confidence': 0.8,
            'columns': group['columns'],
            'primary_identifier': group['columns'][0] if group['columns'] else '',
            'description': group['reasoning'],
            'business_domain': group['entity_type']
        })

        print(f"[DynamicTemplateDetector] Final templates: {len(templates_list)}")
        state['templates'] = templates_list
        state['next'] = 'finalize'
        return state    

    # Step 3: Enrich with ML verification
    print("[DynamicTemplateDetector] Step 3: ML verification...")
    embeddings_cache = {}
    templates = {}

    for template in templates_list:
        template_id = template["template_id"]

        # Add ML-based verification
        enriched_template = enrich_template_with_ml_clustering(
            template, columns, embeddings_cache
        )

        templates[template_id] = enriched_template

        print(
            f"[DynamicTemplateDetector] Found template: {template['template_name']} "
            f"({len(template['columns'])} columns, confidence: {template['confidence']:.2f})"
        )

    # Store results
    state["templates"] = templates
    state["template_analysis"] = {
        "relationship_analysis": relationship_analysis,
        "overall_analysis": template_detection.get("overall_analysis", {}),
        "total_templates_detected": len(templates),
    }

    state["next"] = "generate_template_files"

    print(f"[DynamicTemplateDetector] Detected {len(templates)} distinct templates")

    return state


def generate_template_files_node(state):
    """
    Generate Excel files for each detected template WITH ACTUAL DATA.
    Handles partitioned Parquet files from Spark.
    Tracks transformations and shows before/after comparison.
    """

    from tools.s3_tool import s3, BUCKET
    import pandas as pd
    from io import BytesIO

    job_id = state["job_id"]
    templates = state["templates"]

    print(f"[TemplateFileGenerator] Generating files for {len(templates)} templates")

    # Track transformation metadata
    transformation_metadata = state.get("transformation_metadata", {})
    user_request = transformation_metadata.get("user_request", "")
    new_columns_created = transformation_metadata.get("new_columns", [])

    if user_request:
        print(f"[TemplateFileGenerator] Transformation: {user_request}")
        print(f"[TemplateFileGenerator] New columns: {new_columns_created}")

    jobs_table.update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET current_step = :c, progress = :p",
        ExpressionAttributeValues={
            ":c": "generating_template_files",
            ":p": 65,
        },
    )

    # Find the data directory path and track source type
    data_path = None
    data_source_type = None

    if state.get("transformed_path"):
        data_path = state["transformed_path"].replace(f"s3://{BUCKET}/", "")
        data_source_type = "TRANSFORMED"
        print(f"[TemplateFileGenerator] Using TRANSFORMED data: {data_path}")

    elif state.get("cleaned_path"):
        data_path = state["cleaned_path"].replace(f"s3://{BUCKET}/", "")
        data_source_type = "CLEANED"
        print(f"[TemplateFileGenerator] Using CLEANED data: {data_path}")

    elif state.get("s3_key"):
        data_path = state["s3_key"]
        data_source_type = "ORIGINAL"
        print(f"[TemplateFileGenerator] Using ORIGINAL data: {data_path}")

    if not data_path:
        print("[TemplateFileGenerator] ERROR: No data source found")
        state["template_files"] = []
        state["next"] = "finalize"
        return state

    # Load data - handle both single files and partitioned directories
    try:
        # Determine prefix
        if not data_path.endswith("/"):
            if "/" in data_path:
                data_path_prefix = data_path.rsplit("/", 1)[0] + "/"
            else:
                data_path_prefix = ""
        else:
            data_path_prefix = data_path

        print(f"[TemplateFileGenerator] Listing files in: s3://{BUCKET}/{data_path_prefix}")

        response = s3.list_objects_v2(Bucket=BUCKET, Prefix=data_path_prefix)

        if "Contents" not in response:
            print(f"[TemplateFileGenerator] ERROR: No files found at {data_path_prefix}")
            state["template_files"] = []
            state["next"] = "finalize"
            return state

        # Filter parquet files
        parquet_files = [
            obj["Key"]
            for obj in response["Contents"]
            if obj["Key"].endswith(".parquet") and obj["Size"] > 0
        ]

        print(f"[TemplateFileGenerator] Found {len(parquet_files)} parquet files")

        if parquet_files:
            dfs = []

            for i, parquet_key in enumerate(parquet_files):

                if i < 5 or i % 10 == 0:
                    print(
                        f"[TemplateFileGenerator] Reading file {i+1}/{len(parquet_files)}: "
                        f"{parquet_key.split('/')[-1]}"
                    )

                obj = s3.get_object(Bucket=BUCKET, Key=parquet_key)
                df_chunk = pd.read_parquet(BytesIO(obj["Body"].read()))
                dfs.append(df_chunk)

            full_data = pd.concat(dfs, ignore_index=True)

            print(
                f"[TemplateFileGenerator] Combined {len(dfs)} files: "
                f"{len(full_data)} rows, {len(full_data.columns)} columns"
            )

        else:
            print(f"[TemplateFileGenerator] No parquet files, trying single file: {data_path}")

            obj = s3.get_object(Bucket=BUCKET, Key=data_path)

            if data_path.endswith(".csv"):
                full_data = pd.read_csv(BytesIO(obj["Body"].read()))

            elif data_path.endswith(".xlsx") or data_path.endswith(".xls"):
                full_data = pd.read_excel(BytesIO(obj["Body"].read()))

            elif data_path.endswith(".parquet"):
                full_data = pd.read_parquet(BytesIO(obj["Body"].read()))

            else:
                full_data = pd.read_csv(BytesIO(obj["Body"].read()))

            print(
                f"[TemplateFileGenerator] Loaded single file: "
                f"{len(full_data)} rows, {len(full_data.columns)} columns"
            )

        print(f"[TemplateFileGenerator] Columns: {list(full_data.columns)}")

    except Exception as e:
        print(f"[TemplateFileGenerator] ERROR loading data: {e}")
        import traceback
        traceback.print_exc()

        state["template_files"] = []
        state["next"] = "finalize"
        return state

    # Load previous template data for comparison (if transformation was applied)
    previous_template_data = {}
    if data_source_type == "TRANSFORMED" and state.get("template_files"):
        print("[TemplateFileGenerator] Loading previous data for comparison...")
        for prev_template in state.get("template_files", []):
            csv_key = prev_template.get("csv_data_key")
            if csv_key:
                try:
                    obj = s3.get_object(Bucket=BUCKET, Key=csv_key)
                    prev_df = pd.read_csv(BytesIO(obj["Body"].read()))
                    template_id = prev_template.get("template_id", prev_template["template_name"])
                    previous_template_data[template_id] = prev_df
                    print(f"[TemplateFileGenerator] Loaded previous: {prev_template['template_name']}")
                except Exception as e:
                    print(f"[TemplateFileGenerator] Could not load previous: {e}")

    template_files = []
    user_id = state["s3_key"].split("/")[0]

    templates_list = templates.values() if isinstance(templates, dict) else templates

    for idx, template_data in enumerate(templates_list):

        template_name = template_data["template_name"]
        template_type = template_data["template_type"]
        template_id = template_data.get("template_id", f"TMPL_{idx:03d}")
        columns = template_data["columns"]

        available_columns = []
        missing_columns = []
        column_mapping = {}
        transformed_columns = []

        for col in columns:
            if col in full_data.columns:
                available_columns.append(col)
                column_mapping[col] = col
            else:
                possible_variants = [
                    col.replace('_m', '_km'),
                    col.replace('_meters', '_kilometers'),
                    col.replace('_m', '_miles'),
                    col.replace('_liters', '_gallons'),
                    col + '_transformed',
                ]

                found = False
                for variant in possible_variants:
                    if variant in full_data.columns:
                        available_columns.append(variant)
                        column_mapping[col] = variant
                        transformed_columns.append(variant)
                        found = True
                        break

                if not found:
                    missing_columns.append(col)

        for new_col in new_columns_created:
            if new_col in full_data.columns and new_col not in available_columns:
                available_columns.append(new_col)
                transformed_columns.append(new_col)

        if not available_columns:
            print(f"[TemplateFileGenerator] ERROR: No columns found for {template_name}")
            continue

        template_df = full_data[available_columns].copy()

        csv_buffer = BytesIO()
        template_df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)

        csv_key = f"{user_id}/{job_id}/templates/data/{template_id}.csv"

        s3.put_object(
            Bucket=BUCKET,
            Key=csv_key,
            Body=csv_buffer.getvalue(),
            ContentType="text/csv",
        )

        buffer = BytesIO()

        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:

            template_df.to_excel(writer, sheet_name="Data", index=False)

            metadata_rows = [
                {"Property": "Template ID", "Value": template_id},
                {"Property": "Template Name", "Value": template_name},
                {"Property": "Template Type", "Value": template_type},
                {"Property": "Data Source", "Value": data_source_type},
                {"Property": "Row Count", "Value": len(template_df)},
                {"Property": "Column Count", "Value": f"{len(available_columns)}/{len(columns)}"},
            ]

            metadata_df = pd.DataFrame(metadata_rows)
            metadata_df.to_excel(writer, sheet_name="Metadata", index=False)

        buffer.seek(0)

        template_filename = f"{template_name.replace(' ', '_')}_{template_type}.xlsx"
        template_key = f"{user_id}/{job_id}/templates/{template_filename}"

        s3.put_object(
            Bucket=BUCKET,
            Key=template_key,
            Body=buffer.getvalue(),
            ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        download_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET, "Key": template_key},
            ExpiresIn=3600,
        )

        template_files.append({
            "template_id": template_id,
            "name": template_filename,
            "template_name": template_name,
            "type": template_type,
            "columns": available_columns,
            "row_count": len(template_df),
            "url": download_url,
            "s3_key": template_key,
            "csv_data_key": csv_key,
        })

    state["template_files"] = template_files
    state["next"] = "finalize"

    print(f"[TemplateFileGenerator] Generated {len(template_files)} templates from {data_source_type} data")

    return state