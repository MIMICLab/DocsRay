# docsray/search/vector_search.py

import numpy as np
import torch
from typing import List, Dict, Tuple, Union

def get_device():
    """Get the best available compute device"""
    if torch.cuda.is_available():
        return "cuda"
    elif torch.backends.mps.is_available():
        return "mps"
    else:
        return "cpu"

def cosine_similarity(v1, v2):
    """Simple cosine similarity for single vectors"""
    v1 = np.array(v1)
    v2 = np.array(v2)
    dot = np.dot(v1, v2)
    return dot

def batch_cosine_similarity(query_emb: np.ndarray, embeddings: np.ndarray, device: str = None) -> np.ndarray:
    """
    Compute cosine similarity between a query and multiple embeddings using GPU if available
    
    Args:
        query_emb: Query embedding vector (1D array)
        embeddings: Matrix of embeddings (2D array, each row is an embedding)
        device: Device to use ('cuda', 'mps', 'cpu', or None for auto-detect)
    
    Returns:
        Array of similarity scores
    """
    if device is None:
        device = get_device()
    
    # Convert to tensors and move to device
    query_vec = torch.as_tensor(query_emb, dtype=torch.float32, device=device)
    embed_mat = torch.as_tensor(embeddings, dtype=torch.float32, device=device)
    
    # Compute similarities
    sims = torch.matmul(embed_mat, query_vec)
    
    # Return as numpy array
    return sims.cpu().numpy()

def simple_vector_search(query_emb, index_data: List[Dict], top_k=8):
    """
    Original simple vector search for backward compatibility
    
    Args:
        query_emb: numpy array or list[float]
        index_data: [{"embedding": [...], "metadata": {...}}, ...]
        top_k: Number of top results to return
    
    Returns:
        List of top k results
    """
    results = []
    query_vec = np.array(query_emb)

    for item in index_data:
        emb = np.array(item["embedding"])
        score = cosine_similarity(query_vec, emb)
        results.append((score, item))

    results.sort(key=lambda x: x[0], reverse=True)
    top_results = [r[1] for r in results[:top_k]]
    return top_results

def vector_search_optimized(
    query_emb: Union[List[float], np.ndarray], 
    index_data: List[Dict], 
    top_k: int = 8,
    return_scores: bool = False
) -> Union[List[Dict], List[Tuple[Dict, float]]]:
    """
    Optimized vector search using GPU acceleration and vectorized operations
    
    Args:
        query_emb: Query embedding (list or numpy array)
        index_data: List of dicts with "embedding" and "metadata" keys
        top_k: Number of top results to return
        return_scores: Whether to return similarity scores along with results
    
    Returns:
        List of top k results (optionally with scores)
    """
    if not index_data:
        return []
    
    # Extract embeddings and create matrix
    embeddings = []
    for item in index_data:
        embeddings.append(item["embedding"])
    
    # Convert to numpy array
    embed_mat = np.vstack(embeddings).astype(np.float32)
    query_vec = np.asarray(query_emb, dtype=np.float32)
    
    # Compute similarities using GPU if available
    sims = batch_cosine_similarity(query_vec, embed_mat)
    
    # Partial sort - O(N log k) instead of full sort
    k = min(top_k, len(sims))
    if k == len(sims):
        # If we want all results, just sort everything
        top_idx = np.argsort(-sims)
    else:
        # Use partial sort for efficiency
        top_idx = np.argpartition(-sims, k - 1)[:k]
        top_idx = top_idx[np.argsort(-sims[top_idx])]
    
    # Build results
    if return_scores:
        return [(index_data[idx], float(sims[idx])) for idx in top_idx]
    else:
        return [index_data[idx] for idx in top_idx]

def vector_search_with_metadata(
    query_emb: Union[List[float], np.ndarray],
    embeddings: List[Union[List[float], np.ndarray]],
    metadata: List[Dict],
    top_k: int = 8
) -> List[Tuple[Dict, float]]:
    """
    Vector search when embeddings and metadata are separate
    
    Args:
        query_emb: Query embedding
        embeddings: List of embeddings
        metadata: List of metadata dicts corresponding to embeddings
        top_k: Number of top results to return
    
    Returns:
        List of (metadata, score) tuples
    """
    if not embeddings or len(embeddings) != len(metadata):
        return []
    
    # Convert to numpy array
    embed_mat = np.vstack(embeddings).astype(np.float32)
    query_vec = np.asarray(query_emb, dtype=np.float32)
    
    # Compute similarities
    sims = batch_cosine_similarity(query_vec, embed_mat)
    
    # Get top k
    k = min(top_k, len(sims))
    if k == len(sims):
        top_idx = np.argsort(-sims)
    else:
        top_idx = np.argpartition(-sims, k - 1)[:k]
        top_idx = top_idx[np.argsort(-sims[top_idx])]
    
    # Return results with scores
    return [(metadata[idx], float(sims[idx])) for idx in top_idx]