#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))

import json
from docsray.inference.embedding_model import embedding_model

def build_chunk_index(chunks):
    """
    Args
    ----
    chunks : list of dict
        Expected format:
            [{ "content": "...", "section_title": "...", ... }, ...]

    The function embeds each *content* entry using the embedding model and
    returns a list of dictionaries in the form:

        [{ "embedding": [...], "metadata": {...} }, ...]
    """
    
    contents = [c["content"] for c in chunks]
    embeddings = embedding_model.get_embeddings(contents)  # shape: (N, emb_dim)

    index_data = []
    for i, emb in enumerate(embeddings):
        index_data.append({
            "embedding": emb.tolist(),
            "metadata": chunks[i]
        })
    return index_data

if __name__ == "__main__":
    chunk_folder = "data/chunks"
    index_folder = "data/index"
    os.makedirs(index_folder, exist_ok=True)

    for fname in os.listdir(chunk_folder):
        if fname.endswith("_chunks.json"):
            path = os.path.join(chunk_folder, fname)
            with open(path, 'r', encoding='utf-8') as f:
                chunked_data = json.load(f)

            index_data = build_chunk_index(chunked_data)

            base_name = os.path.splitext(fname)[0]
            out_path = os.path.join(index_folder, f"{base_name}_vectors.json")
            with open(out_path, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)

    print("Build index complete.")