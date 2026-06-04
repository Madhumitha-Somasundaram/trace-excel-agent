import boto3
import json
import os
from typing import Dict, Any, Optional

# Initialize AWS Bedrock client
bedrock = boto3.client(
    service_name='bedrock-runtime',
    region_name=os.getenv('AWS_REGION', 'us-east-1')
)

MODEL_ID = "us.anthropic.claude-haiku-4-5-20251001-v1:0"


def llm_call(
    prompt: str,
    max_tokens: int = 4096,
    temperature: float = 0.7,
    system_prompt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Call AWS Bedrock Claude for reasoning and analysis.

    Args:
        prompt: The user/task prompt
        max_tokens: Maximum tokens to generate
        temperature: Sampling temperature (0-1)
        system_prompt: Optional system prompt for context

    Returns:
        Parsed JSON response from Claude
    """

    messages = [
        {
            "role": "user",
            "content": prompt
        }
    ]

    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": messages,
        "temperature": temperature
    }

    if system_prompt:
        request_body["system"] = system_prompt

    try:
        response = bedrock.invoke_model(
            modelId=MODEL_ID,
            body=json.dumps(request_body)
        )

        response_body = json.loads(response['body'].read())
        content = response_body['content'][0]['text']

        # Check if response was truncated
        stop_reason = response_body.get('stop_reason')
        if stop_reason == 'max_tokens':
            print(f"⚠️  WARNING: Response truncated at max_tokens ({max_tokens})")
            print(f"[DEBUG] Content length: {len(content)} chars")

        print(f"[DEBUG] Raw response content: {content}...")

        # Try to parse as JSON if possible
        try:
            # Strip markdown code fences if present
            cleaned = content.strip()
            if cleaned.startswith('```json'):
                cleaned = cleaned[7:]  # Remove ```json
            elif cleaned.startswith('```'):
                cleaned = cleaned[3:]  # Remove ```
            if cleaned.endswith('```'):
                cleaned = cleaned[:-3]  # Remove trailing ```
            cleaned = cleaned.strip()

            # Try to fix incomplete JSON (common when truncated)
            if not cleaned.endswith('}'):
                print(f"⚠️  Attempting to fix incomplete JSON")
                # Count braces to attempt recovery
                open_braces = cleaned.count('{')
                close_braces = cleaned.count('}')
                if open_braces > close_braces:
                    # Try to close unclosed strings first
                    if cleaned.count('"') % 2 != 0:
                        cleaned += '"'
                    # Add missing closing braces
                    cleaned += '}' * (open_braces - close_braces)
                    print(f"[DEBUG] Added {open_braces - close_braces} closing braces")

            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            print(f"❌ JSON parse failed after cleaning: {str(e)}")
            print(f"[DEBUG] First 200 chars: {cleaned[:200]}")
            print(f"[DEBUG] Last 200 chars: {cleaned[-200:]}")
            # If not JSON, return raw text wrapped in dict
            return {"response": content, "parse_error": str(e)}

    except Exception as e:
        print(f"LLM call error: {str(e)}")
        return {"error": str(e)}


def llm_call_streaming(prompt: str, callback):
    """
    Streaming LLM call for real-time chat responses.

    Args:
        prompt: The user prompt
        callback: Function to call with each chunk
    """
    messages = [{"role": "user", "content": prompt}]

    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "messages": messages,
        "temperature": 0.7
    }

    try:
        response = bedrock.invoke_model_with_response_stream(
            modelId=MODEL_ID,
            body=json.dumps(request_body)
        )

        stream = response.get('body')
        if stream:
            for event in stream:
                chunk = json.loads(event['chunk']['bytes'])
                if chunk['type'] == 'content_block_delta':
                    text = chunk['delta'].get('text', '')
                    if text:
                        callback(text)

    except Exception as e:
        print(f"Streaming LLM error: {str(e)}")
        callback(f"Error: {str(e)}")


def analyze_columns_for_template(columns: list) -> Dict[str, Any]:
    """
    Use LLM to identify template type from column names.

    Args:
        columns: List of column names from Excel

    Returns:
        Template detection result with type and confidence
    """
    prompt = f"""You are a data analysis expert. Analyze these Excel column names and identify the template type.

Column names:
{json.dumps(columns, indent=2)}

Common template types:
- Transportation: vehicle_id, route, distance, fuel, driver, delivery_date, shipment
- Employee: employee_id, name, department, salary, hire_date, position, email
- Finance: transaction_id, amount, date, account, category, balance
- Inventory: product_id, sku, quantity, warehouse, supplier, reorder_level
- Sales: order_id, customer, product, quantity, price, revenue, date
- Logistics: tracking_number, origin, destination, weight, carrier, status

Return JSON with:
{{
  "template_type": "transportation|employee|finance|inventory|sales|logistics|custom",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation",
  "suggested_columns": ["list", "of", "key", "columns"],
  "domain": "business domain name"
}}"""

    return llm_call(prompt, max_tokens=1024, temperature=0.3)


def generate_transformation_code(
    user_request: str,
    columns: list,
    sample_data: Dict[str, list]
) -> Dict[str, Any]:
    """
    Generate PySpark transformation code based on user's natural language request.

    Args:
        user_request: User's transformation request (e.g., "convert distance from m to km")
        columns: Available columns
        sample_data: Sample rows for context

    Returns:
        Generated PySpark code and explanation
    """
    prompt = f"""You are a PySpark expert. Generate transformation code based on user request.

User request: "{user_request}"

Available columns: {columns}

Sample data (first 3 rows):
{json.dumps(sample_data, indent=2)}

Generate PySpark transformation code that:
1. Uses DataFrame API (not SQL unless requested)
2. Handles null values safely
3. Is production-ready and efficient
4. Includes comments explaining the logic

Return JSON:
{{
  "code": "complete PySpark code as string",
  "explanation": "brief explanation of what the code does",
  "affected_columns": ["list of columns modified"],
  "new_columns": ["list of new columns created"],
  "dependencies": ["required PySpark functions/imports"]
}}

IMPORTANT: Keep the code concise but complete. The entire JSON response must fit within token limits."""

    return llm_call(prompt, max_tokens=8192, temperature=0.2)


def cluster_columns_semantically(columns: list) -> Dict[str, Any]:
    """
    Use LLM to semantically group related columns.

    Args:
        columns: List of column names

    Returns:
        Grouped columns with semantic labels
    """
    prompt = f"""You are a data modeling expert. Group these columns into semantic clusters.

Columns:
{json.dumps(columns, indent=2)}

Group related columns together (e.g., all date fields, all location fields, all monetary fields).
Provide meaningful business names for each cluster.

Return JSON:
{{
  "clusters": {{
    "cluster_name_1": {{
      "columns": ["col1", "col2"],
      "description": "what this group represents",
      "data_type": "temporal|spatial|monetary|categorical|identifier|metric"
    }},
    ...
  }}
}}"""

    return llm_call(prompt, max_tokens=2048, temperature=0.4)
