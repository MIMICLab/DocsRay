#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))

import json
import numpy as np
from docsray.inference.embedding_model import embedding_model


def build_section_reps(sections, chunk_index):
    """
    Args
    ----
    sections : list[dict]
        Example element:
            { "title": "Chapter 2 Installation", "start_page": 10,
              "end_page": 19, ... }

    chunk_index : list[dict]
        Example element:
            { "embedding": [...],
              "metadata": { "section_title": "...", ... } }

    The function embeds each section title and computes the mean of all
    chunk embeddings that belong to that section.  It appends two fields
    to every section dictionary:

        - sec["title_emb"]      : embedding of the section title
        - sec["avg_chunk_emb"]  : average embedding of chunks inside the section

    Returns
    -------
    list[dict]
        The updated *sections* list with the two new embedding fields.
    """
    
    # 1) Section title embeddings (batch)
    titles = [sec["title"] for sec in sections]
    title_embs = embedding_model.get_embeddings(titles)  # shape: (num_sections, dim)
    for i, sec in enumerate(sections):
        sec["title_emb"] = title_embs[i].tolist()

    # 2) Collect chunks per section
    section2embs = {}
    for item in chunk_index:
        sec_t = item["metadata"]["section_title"]
        emb = item["embedding"]  # list[float]
        if sec_t not in section2embs:
            section2embs[sec_t] = []
        section2embs[sec_t].append(emb)

    # 3) Average chunk embedding within each section
    for sec in sections:
        stitle = sec["title"]
        if stitle not in section2embs:
            sec["avg_chunk_emb"] = None
        else:
            arr = np.array(section2embs[stitle])  # shape: (num_chunks, emb_dim)
            avg_vec = arr.mean(axis=0)            # (emb_dim,)
            sec["avg_chunk_emb"] = avg_vec.tolist()
    
    return sections

if __name__ == "__main__":
    # Example: TOC‑based section metadata
    sections_json = "data/extracted/sections.json"
    # Example: pre‑computed chunk embeddings
    chunk_index_json = "data/index/sample_chunks_vectors.json"

    with open(sections_json, 'r', encoding='utf-8') as f:
        sections_data = json.load(f)
    
    with open(chunk_index_json, 'r', encoding='utf-8') as f:
        chunk_index_data = json.load(f)

    # Build representative vectors for each section
    updated_sections = build_section_reps(sections_data, chunk_index_data)

    # Save the updated sections with embeddings
    out_path = "data/extracted/sections_with_emb.json"
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(updated_sections, f, ensure_ascii=False, indent=2)

    print("Section reps built and saved.")