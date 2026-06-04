"""
Column clustering node using AWS Bedrock embeddings + DBSCAN
"""
import os
import boto3
import json
from tools.bedrock_embeddings import cluster_columns_semantically
from tools.llm import llm_call
from agent_runtime.events.emitter import emit

REGION = os.environ.get('AWS_REGION', 'us-east-1')
ddb = boto3.resource('dynamodb', region_name=REGION)
jobs_table = ddb.Table('jobs')


def cluster_node(state):
    """
    Cluster columns into semantic groups using Bedrock embeddings + DBSCAN.

    This uses AWS Bedrock Titan Embeddings for semantic similarity
    and DBSCAN for automatic clustering - no heavy ML dependencies!
    """

    job_id = state.get('job_id')
    columns = state.get("columns", [])

    print(f"[ClusterNode] Clustering {len(columns)} columns using Bedrock embeddings")

    emit(job_id, "cluster_node", "running", "Clustering columns semantically with Bedrock...", 30)

    # Update DynamoDB progress
    jobs_table.update_item(
        Key={'job_id': job_id},
        UpdateExpression='SET current_step = :c, progress = :p',
        ExpressionAttributeValues={
            ':c': 'clustering_columns',
            ':p': 30
        }
    )

    try:
        # Use Bedrock embeddings + DBSCAN for semantic clustering
        clusters = cluster_columns_semantically(columns, eps=0.35, min_samples=2)

        # Use LLM to label clusters with meaningful names
        cluster_prompt = f"""You are analyzing semantic clusters of Excel columns.

Give each cluster a descriptive business name based on what the columns represent.

Clusters:
{json.dumps(clusters, indent=2)}

Return JSON with cluster labels:
{{
  "original_cluster_name": "Business-Friendly Name",
  ...
}}

Examples:
- cluster_0 with [employee_id, name, department] → "Employee Information"
- cluster_1 with [amount, price, cost] → "Financial Data"
- cluster_2 with [vehicle_id, route, distance] → "Transportation Data"
"""

        label_response = llm_call(cluster_prompt, max_tokens=512)

        # Rename clusters with LLM-generated names
        if isinstance(label_response, dict):
            labeled_clusters = {}
            for old_name, new_name in label_response.items():
                if old_name in clusters:
                    labeled_clusters[new_name] = clusters[old_name]
                else:
                    # Keep original if no mapping
                    labeled_clusters[old_name] = clusters.get(old_name, [])

            # Add any unmapped clusters
            for cluster_name, cluster_cols in clusters.items():
                if cluster_name not in label_response:
                    labeled_clusters[cluster_name] = cluster_cols

            clusters = labeled_clusters

        print(f"[ClusterNode] Created {len(clusters)} semantic clusters:")
        for name, cols in clusters.items():
            print(f"  - {name}: {len(cols)} columns")

        # Update state
        state["clusters"] = clusters
        state["next"] = "dynamic_template_detection"

        emit(job_id, "cluster_node", "completed", f"Created {len(clusters)} semantic clusters", 40)

        jobs_table.update_item(
            Key={'job_id': job_id},
            UpdateExpression='SET current_step = :c, progress = :p',
            ExpressionAttributeValues={
                ':c': 'clusters_created',
                ':p': 40
            }
        )

    except Exception as e:
        print(f"[ClusterNode] Error: {e}")
        import traceback
        traceback.print_exc()

        # Fallback: simple pattern-based clustering
        clusters = {
            "Identifiers": [c for c in columns if "id" in c.lower()],
            "Names & Labels": [c for c in columns if "name" in c.lower() or "label" in c.lower()],
            "Dates & Times": [c for c in columns if any(x in c.lower() for x in ["date", "time", "created", "updated", "timestamp"])],
            "Financial": [c for c in columns if any(x in c.lower() for x in ["amount", "price", "cost", "value", "salary", "payment"])],
            "Other": [c for c in columns if not any(c in sum(clusters.values(), []) for clusters in [{"Identifiers": [], "Names & Labels": [], "Dates & Times": [], "Financial": []}])]
        }

        # Remove empty clusters
        clusters = {k: v for k, v in clusters.items() if v}

        state["clusters"] = clusters
        state["next"] = "dynamic_template_detection"

        emit(job_id, "cluster_node", "completed", f"Fallback clustering: {len(clusters)} groups", 40)

    return state

