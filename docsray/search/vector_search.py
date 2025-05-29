# src/search/vector_search.py

import numpy as np
from typing import List, Dict

def cosine_similarity(v1, v2):
    v1 = np.array(v1)
    v2 = np.array(v2)
    dot = np.dot(v1, v2)
    return dot

def simple_vector_search(query_emb, index_data: List[Dict], top_k=8):
    """
    query_emb: numpy array or list[float]
    index_data: [{"embedding": [...], "metadata": {...}}, ...]
    """
    results = []
    query_vec = np.array(query_emb)

    for item in index_data:
        emb = np.array(item["embedding"])
        score = cosine_similarity(query_vec, emb)  # ← 함수 재사용
        results.append((score, item))

    results.sort(key=lambda x: x[0], reverse=True)
    top_results = [r[1] for r in results[:top_k]]
    return top_results