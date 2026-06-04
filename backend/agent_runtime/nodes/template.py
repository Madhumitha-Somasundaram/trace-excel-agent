from tools.llm import analyze_columns_for_template
import os
from tools.s3_tool import s3, BUCKET
import boto3
import json
import pandas as pd
from io import BytesIO

ddb = boto3.resource('dynamodb', region_name=os.environ.get("AWS_REGION", "us-east-1"))
jobs_table = ddb.Table('jobs')


def template_node(state):
    """
    Detect template types and generate downloadable Excel templates.

    Creates:
    1. Template type detection (Transportation, Employee, etc.)
    2. Excel templates for each detected type
    3. S3 URLs for download
    """
    import os

    job_id = state['job_id']
    columns = state["columns"]
    clusters = state["clusters"]

    print(f"[TemplateNode] Detecting templates from {len(clusters)} clusters")

    jobs_table.update_item(
        Key={'job_id': job_id},
        UpdateExpression='SET current_step = :c, progress = :p',
        ExpressionAttributeValues={
            ':c': 'generating_templates',
            ':p': 60
        }
    )

    # Analyze overall dataset for primary template type
    template_analysis = analyze_columns_for_template(columns)

    templates = {}
    template_files = []

    # Create template for each cluster
    for cluster_name, cluster_data in clusters.items():
        cluster_cols = cluster_data.get('columns', [])

        # Detect specific template type for this cluster
        cluster_template = analyze_columns_for_template(cluster_cols)

        template_type = cluster_template.get('template_type', 'custom')
        confidence = cluster_template.get('confidence', 0.0)

        # Create Excel template with headers
        template_df = pd.DataFrame(columns=cluster_cols)

        # Add example row to show format
        example_row = {col: f"<{col}>" for col in cluster_cols}
        template_df = pd.concat([template_df, pd.DataFrame([example_row])], ignore_index=True)

        # Save to S3
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            template_df.to_excel(writer, index=False, sheet_name='Template')

        buffer.seek(0)

        user_id = state['s3_key'].split('/')[0]
        template_key = f"{user_id}/{job_id}/templates/{cluster_name}_{template_type}.xlsx"

        s3.put_object(
            Bucket=BUCKET,
            Key=template_key,
            Body=buffer.getvalue(),
            ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

        # Generate presigned URL (valid for 1 hour)
        download_url = s3.generate_presigned_url(
            'get_object',
            Params={'Bucket': BUCKET, 'Key': template_key},
            ExpiresIn=3600
        )

        templates[cluster_name] = {
            "template_type": template_type,
            "confidence": confidence,
            "columns": cluster_cols,
            "description": cluster_data.get('description', ''),
            "data_type": cluster_data.get('data_type', 'unknown'),
            "s3_key": template_key,
            "download_url": download_url
        }

        template_files.append({
            "name": f"{cluster_name}_{template_type}.xlsx",
            "type": template_type,
            "url": download_url
        })

        print(f"[TemplateNode] Created template: {cluster_name} ({template_type})")

    # Save template metadata to S3
    user_id = state['s3_key'].split('/')[0]
    metadata_key = f"{user_id}/{job_id}/templates/metadata.json"

    s3.put_object(
        Bucket=BUCKET,
        Key=metadata_key,
        Body=json.dumps({
            'primary_template': template_analysis,
            'templates': templates,
            'template_files': template_files
        }, indent=2),
        ContentType='application/json'
    )

    state["templates"] = templates
    state["template_files"] = template_files
    state["next"] = "finalize"

    print(f"[TemplateNode] Generated {len(templates)} templates")

    return state