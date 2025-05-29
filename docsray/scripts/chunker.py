#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
import os
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))

import json
from typing import List, Dict, Any
from docsray.utils.text_cleaning import basic_clean_text

# --- Token helpers ---------------------------------------------------------
try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")
    def _tokenize(txt: str) -> list[int]:
        return _enc.encode(txt)
    def _detokenize(tok_ids: list[int]) -> str:
        return _enc.decode(tok_ids)
except ModuleNotFoundError:
    # Fallback to simple whitespace tokenisation
    def _tokenize(txt: str) -> list[str]:
        return txt.split()
    def _detokenize(tokens: list[str]) -> str:
        return " ".join(tokens)
# --------------------------------------------------------------------------

# Tune these two to balance chunk length and redundancy
CHUNK_TOKENS =  550 # tokens per chunk
OVERLAP_TOKENS = 25  # tokens of overlap between consecutive chunks

def get_section_of_page(page_num: int, toc: List[List[Any]]) -> str:
    """
    Get the section title for a given page number based on the table of contents.
    toc: List of tuples (level, title, start_page)
    page_num: 0-indexed page number
    """ 
    current_section = "Others"
    for (lvl, title, start_p) in toc:
        if page_num + 1 >= start_p:
            current_section = title
        else:
            break
    return current_section

def chunk_text(text: str,
               chunk_size: int = CHUNK_TOKENS,
               overlap: int = OVERLAP_TOKENS) -> List[str]:
    """
    Split *text* into chunks of `chunk_size` tokens with `overlap` tokens
    of context shared between consecutive chunks.
    The function uses tiktoken when available; otherwise it falls back to
    whitespace tokenisation.
    """
    text = basic_clean_text(text)
    if not text:
        return []

    tokens = _tokenize(text)
    chunks: List[str] = []
    start = 0
    step = max(chunk_size - overlap, 1)  # avoid infinite loop

    while start < len(tokens):
        end = start + chunk_size
        chunk_tokens = tokens[start:end]
        if chunk_tokens:
            chunks.append(_detokenize(chunk_tokens).strip())
        if end >= len(tokens):
            break
        start += step
    return chunks

def process_extracted_file(json_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    json_data: {
      "file_path": "...",
      "toc": [(level, title, start_page), ...],
      "pages_text": ["page0 text", "page1 text", ...]
    }
    """
    pdf_path = json_data["file_path"]

    toc = [(0, s["title"], s["start_page"]) for s in json_data["sections"]]
    pages_text = json_data["pages_text"]

    chunked_result = []
    for page_idx, text in enumerate(pages_text):
        section_title = get_section_of_page(page_idx, toc)
        # chunkify
        splitted = chunk_text(text)
        for c_i, c_text in enumerate(splitted):
            chunked_result.append({
                "file_path": pdf_path,
                "page_idx": page_idx,
                "section_title": section_title,
                "chunk_index": c_i,
                "content": c_text
            })
    return chunked_result

if __name__ == "__main__":
    extracted_folder = "data/extracted"
    os.makedirs(extracted_folder, exist_ok=True)
    chunk_folder = "data/chunks"
    os.makedirs(chunk_folder, exist_ok=True)

    for fname in os.listdir(extracted_folder):
        # sections.json 파일은 건너뛰기
        if fname.endswith(".json") and fname != "sections.json":
            path = os.path.join(extracted_folder, fname)
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            chunked_data = process_extracted_file(data)

            base_name = os.path.splitext(fname)[0]
            out_json = os.path.join(chunk_folder, f"{base_name}_chunks.json")
            with open(out_json, 'w', encoding='utf-8') as f:
                json.dump(chunked_data, f, ensure_ascii=False, indent=2)

    print("Chunking Complete.")