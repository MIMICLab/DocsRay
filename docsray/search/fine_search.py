# src/search/fine_search.py
import numpy as np
import torch

def fine_search_chunks(query_emb,
                       chunk_index,
                       target_sections,
                       top_k: int = 10,
                       fine_only: bool = False):
    """
    Find the most relevant text chunks within the specified sections.

    Parameters
    ----------
    query_emb : list[float] | np.ndarray
        Embedding vector of the user query.
    chunk_index : list[dict]
        Each element is a dictionary like:
        {
            "embedding": [...],
            "metadata": {"section_title": "...", ...}
        }
    target_sections : list[dict]
        Sections to search within, e.g.,
        [
            {"title": "Section 2 Installation Guide", ...},
            ...
        ]
    top_k : int, default = 10
        Number of top‑scoring chunks to return.

    Notes
    -----
    - Only chunks whose ``section_title`` appears in *target_sections* are considered.
    - Cosine similarity is computed between the query embedding and each candidate
      chunk. The chunks are then sorted in descending order of similarity and the
      top *k* results are returned.
    """

# -------------------------------------------------------------
    # 1. Fast membership test — convert section titles to a set.
    # -------------------------------------------------------------
    section_title_set = {sec["title"] for sec in target_sections}

    # -------------------------------------------------------------
    # 2. Filter candidates by section, unless fine_only is requested.
    # -------------------------------------------------------------
    if fine_only:
        candidates = chunk_index
    else:
        candidates = [
            item
            for item in chunk_index
            if item["metadata"]["section_title"] in section_title_set
        ] or chunk_index  # fall back to full index if filter is empty

    # -------------------------------------------------------------
    # 3. Vectorise search — build a single (N, D) matrix on CPU,
    #    then optionally move to GPU for the dot product.
    # -------------------------------------------------------------
    embed_mat = np.vstack([c["embedding"] for c in candidates]).astype(np.float32)
    query_vec = np.asarray(query_emb, dtype=np.float32)

    # ---------- set up compute device ----------
    if torch.cuda.is_available():
        device = "cuda"
    elif torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"
    # -------- GPU path --------
    embed_mat_t = torch.as_tensor(embed_mat, device=device)
    query_vec_t = torch.as_tensor(query_vec, device=device)
    sims_t = torch.matmul(embed_mat_t, query_vec_t)         # (N,)
    sims = sims_t.cpu().numpy()                             # back to CPU


    # -------------------------------------------------------------
    # 5. Partial sort — O(N log k) instead of full sort.
    # -------------------------------------------------------------
    k = min(top_k, sims.shape[0])
    top_idx = np.argpartition(-sims, k - 1)[:k]                 # unsorted top-k
    top_idx = top_idx[np.argsort(-sims[top_idx])]               # sort descending

    return [candidates[i] for i in top_idx]