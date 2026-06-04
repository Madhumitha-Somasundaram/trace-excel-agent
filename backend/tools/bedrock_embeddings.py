"""
AWS Bedrock Embeddings for semantic clustering
Uses Amazon Titan Embeddings instead of sentence-transformers
"""
import boto3
import json
import numpy as np
from typing import List
import os

REGION = os.environ.get('AWS_REGION', 'us-east-1')
bedrock_runtime = boto3.client('bedrock-runtime', region_name=REGION)

# Amazon Titan Embeddings model
EMBEDDING_MODEL = "amazon.titan-embed-text-v1"


def get_embeddings(texts: List[str]) -> np.ndarray:
    """
    Get embeddings for a list of texts using AWS Bedrock Titan Embeddings.

    Args:
        texts: List of text strings to embed

    Returns:
        numpy array of shape (len(texts), embedding_dim)
    """
    embeddings = []

    for text in texts:
        try:
            # Call Bedrock Titan Embeddings
            response = bedrock_runtime.invoke_model(
                modelId=EMBEDDING_MODEL,
                contentType="application/json",
                accept="application/json",
                body=json.dumps({
                    "inputText": text
                })
            )

            # Parse response
            response_body = json.loads(response['body'].read())
            embedding = response_body.get('embedding', [])
            embeddings.append(embedding)

        except Exception as e:
            print(f"Error getting embedding for '{text}': {e}")
            # Fallback: use zero vector
            embeddings.append([0.0] * 1536)  # Titan embedding dimension

    return np.array(embeddings)


def cluster_columns_semantically(columns: List[str], eps: float = 0.3, min_samples: int = 2) -> dict:
    """
    Cluster columns semantically using Bedrock embeddings and DBSCAN.

    Args:
        columns: List of column names
        eps: DBSCAN epsilon parameter (distance threshold)
        min_samples: Minimum samples per cluster

    Returns:
        Dictionary mapping cluster names to column lists
    """
    from sklearn.cluster import DBSCAN
    from sklearn.metrics.pairwise import cosine_similarity

    # Get embeddings from Bedrock
    print(f"[Bedrock] Getting embeddings for {len(columns)} columns...")
    embeddings = get_embeddings(columns)

    # Compute similarity matrix
    similarity_matrix = cosine_similarity(embeddings)

    # Convert to distance matrix
    distance_matrix = 1 - similarity_matrix

    # Cluster with DBSCAN
    clustering = DBSCAN(eps=eps, min_samples=min_samples, metric='precomputed')
    labels = clustering.fit_predict(distance_matrix)

    # Group columns by cluster
    clusters = {}
    for idx, label in enumerate(labels):
        if label == -1:
            cluster_name = f"unclustered_{idx}"
        else:
            cluster_name = f"cluster_{label}"

        if cluster_name not in clusters:
            clusters[cluster_name] = []
        clusters[cluster_name].append(columns[idx])

    print(f"[Bedrock] Created {len(clusters)} semantic clusters")

    return clusters


def get_column_similarity(col1: str, col2: str) -> float:
    """
    Get semantic similarity between two column names.

    Returns:
        Similarity score between 0 and 1
    """
    embeddings = get_embeddings([col1, col2])

    # Compute cosine similarity
    from sklearn.metrics.pairwise import cosine_similarity
    similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]

    return float(similarity)
