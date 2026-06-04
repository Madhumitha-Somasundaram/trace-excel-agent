from sentence_transformers import SentenceTransformer
import os
from sklearn.cluster import DBSCAN
import numpy as np
from tools.llm import llm_call, cluster_columns_semantically
import boto3

model = SentenceTransformer("all-MiniLM-L6-v2")
ddb = boto3.resource('dynamodb', region_name=os.environ.get("AWS_REGION", "us-east-1"))
jobs_table = ddb.Table('jobs')


def cluster_node(state):
    """
    Cluster columns into semantic groups using embeddings + LLM.

    Combines:
    1. Sentence embeddings for structural similarity
    2. DBSCAN clustering for automatic grouping
    3. LLM for semantic labeling and business context
    """
import os

    job_id = state['job_id']
    columns = state["columns"]

    print(f"[ClusterNode] Clustering {len(columns)} columns")

    jobs_table.update_item(
        Key={'job_id': job_id},
        UpdateExpression='SET current_step = :c, progress = :p',
        ExpressionAttributeValues={
            ':c': 'clustering_columns',
            ':p': 50
        }
    )

    # STEP 1: Generate embeddings
    embeddings = model.encode(columns)

    # STEP 2: DBSCAN clustering
    labels = DBSCAN(eps=0.7, min_samples=1, metric="cosine").fit_predict(embeddings)

    raw_clusters = {}
    for col, label in zip(columns, labels):
        raw_clusters.setdefault(int(label), []).append(col)

    print(f"[ClusterNode] Found {len(raw_clusters)} initial clusters")

    # STEP 3: Use LLM for semantic understanding
    llm_result = cluster_columns_semantically(columns)

    if 'clusters' in llm_result:
        final_clusters = llm_result['clusters']
    else:
        # Fallback: use raw clusters with basic naming
        final_clusters = {}
        for cluster_id, cols in raw_clusters.items():
            cluster_name = f"group_{cluster_id}"
            final_clusters[cluster_name] = {
                "columns": cols,
                "description": f"Column group {cluster_id}",
                "data_type": "unknown"
            }

    state["clusters"] = final_clusters
    state["next"] = "template"

    print(f"[ClusterNode] Created {len(final_clusters)} semantic clusters")

    return state