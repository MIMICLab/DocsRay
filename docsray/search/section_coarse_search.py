# src/search/section_coarse_search.py
import numpy as np
import torch

def coarse_search_sections(query_emb,
                           sections: list,
                           beta: float = 0.5,
                           top_k: int = 5):            # <─ new flag
    """
    Vector-ised coarse section ranking.

    Parameters
    ----------
    query : str
        User query text.
    sections : list[dict]
        Each element must contain pre-computed, *L2-normalised* embeddings:
          - "title_emb"      : list[float]
          - "avg_chunk_emb"  : list[float]
    beta : float, default = 0.3
        Interpolation weight between title similarity and average-chunk similarity.
    top_k : int, default = 5
        Number of top-scoring sections to return.

    Returns
    -------
    list[dict]
        Top-k sections sorted by combined similarity score.
    """

    # ---------- set up compute device ----------
    if torch.cuda.is_available():
        device = "cuda"
    elif torch.backends.mps.is_available():
        device = "mps"
    else:
        device = "cpu"
    # 1. gather embeddings --------------------------------------------
    title_list, chunk_list, meta_list = [], [], []
    for sec in sections:
        t_emb, c_emb = sec.get("title_emb"), sec.get("avg_chunk_emb")
        if t_emb is None or c_emb is None:
            continue
        title_list.append(t_emb)
        chunk_list.append(c_emb)
        meta_list.append(sec)
    if not meta_list:
        return []

    # 2. numpy → torch tensors (float32) ------------------------------
    title_mat = torch.as_tensor(title_list, dtype=torch.float32, device=device)
    chunk_mat = torch.as_tensor(chunk_list, dtype=torch.float32, device=device)
    query_vec = torch.as_tensor(query_emb, dtype=torch.float32, device=device)

    # 3. dot product = cosine similarity ------------------------------
    sim_title  = title_mat @ query_vec          # shape (N,)
    sim_chunk  = chunk_mat @ query_vec
    final_sims = beta * sim_title + (1 - beta) * sim_chunk

    # 4. top-k on CPU for ease of use ---------------------------------
    sims_cpu = final_sims.cpu().numpy()
    k = min(top_k, sims_cpu.shape[0])
    idx = np.argpartition(-sims_cpu, k - 1)[:k]
    idx = idx[np.argsort(-sims_cpu[idx])]

    return [meta_list[i] for i in idx]