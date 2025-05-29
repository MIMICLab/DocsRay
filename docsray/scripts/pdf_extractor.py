#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import sys
import os
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))

import fitz  # PyMuPDF
from typing import Dict, Any, List

import io
import pytesseract
from PIL import Image
import pandas as pd
import numpy as np
import cv2
from sklearn.cluster import KMeans

# LLM for outline generation

from docsray.inference.llm_model import get_llm_models


def build_sections_from_layout(pages_text: List[str],
                               init_chunk: int = 5,
                               min_pages: int = 3,
                               max_pages: int = 15,
                               fast_mode: bool = False,
                               preview_chars: int = 1000) -> List[Dict[str, Any]]:
    """
    Build pseudo‑TOC sections for a PDF lacking an explicit table of
    contents.  Pipeline:
      1) Split pages into fixed blocks of `init_chunk` pages.
      2) For every proposed boundary, ask the local LLM whether the
         adjacent pages cover the same topic.  Merge blocks if so.
      3) For each final block, ask the LLM to propose a short title.
    Returns a list of dicts identical in structure to build_sections_from_toc.
    """
    local_llm, local_llm_large = get_llm_models()

    total_pages = len(pages_text)
    if total_pages == 0:
        return []

    # ------------------------------------------------------------------
    # 1. Initial coarse blocks
    # ------------------------------------------------------------------
    boundaries = list(range(0, total_pages, init_chunk))
    if boundaries[-1] != total_pages:
        boundaries.append(total_pages)  # ensure last

    # ------------------------------------------------------------------
    # 2. Boundary verification with LLM
    # ------------------------------------------------------------------
    verified = [0]  # always start at page 1 (idx 0)
    for b in boundaries[1:]:
        a_idx = b - 1  # last page of previous block
        if a_idx < 0 or a_idx >= total_pages - 1:
            verified.append(b)
            continue

        prompt = (
            "Below are short excerpts from two consecutive pages.\n"
            "If both excerpts discuss the same topic, reply with '0'. "
            "If the second excerpt introduces a new topic, reply with '1'. "
            "Reply with a single character only.\n\n"
            f"[Page A]\n{pages_text[a_idx][:400]}\n\n"
            f"[Page B]\n{pages_text[a_idx+1][:400]}\n\n"
        )
        try:
            if fast_mode:
                # Use the smaller model for faster response
                resp = local_llm.generate(prompt).strip()
                resp = resp.split('<start_of_turn>model')[1].split('<end_of_turn>')[0].strip()
            else:
                resp = local_llm_large.generate(prompt).strip()
                resp = resp.split('<|im_start|>assistant')[1].split('<|im_end|>')[0].strip()

            if "0" in resp:
                same_topic = True 
            else:
                same_topic = False
        except Exception:
            same_topic = False  # fail‑closed: assume new topic

        if not same_topic:
            verified.append(b)

    if verified[-1] != total_pages:
        verified.append(total_pages)

    # Convert boundary indices → (start, end) 0‑based
    segments = []
    for i in range(len(verified) - 1):
        s, e = verified[i], verified[i + 1]
        # adjust size constraints
        length = e - s
        if length < min_pages and segments:
            # merge with previous
            segments[-1] = (segments[-1][0], e)
        elif length > max_pages:
            mid = s + max_pages
            segments.append((s, mid))
            segments.append((mid, e))
        else:
            segments.append((s, e))

    # ------------------------------------------------------------------
    # 3. Title generation for each segment
    # ------------------------------------------------------------------
        prompt_template = (
        "Here is a passage from the document.\n"
        f"Please propose ONE concise title that captures its main topic.\n\n"
        "{sample}\n\n"
        "Return ONLY the title text, without any additional commentary or formatting.\n\n"
    )
    sections: List[Dict[str, Any]] = []
    for start, end in segments:
        sample_text = " ".join(pages_text[start:end])[:preview_chars]
        title_prompt = prompt_template.format(sample=sample_text)
        try:
            title_resp = local_llm.generate(title_prompt)
            title_line = title_resp.split('<start_of_turn>model')[1].split('<end_of_turn>')[0].strip()
        except Exception:
            title_line = f"Miscellaneous Section {start + 1}-{end}"

        sections.append({
            "title": title_line,
            "start_page": start + 1,  # 1‑based
            "end_page": end,
            "method": "LLM-Outline"
        })

    return sections

# ────────────────────────────────────────────────
# OCR and multi‑column handling helpers
# ────────────────────────────────────────────────
def ocr_page_words(page, dpi: int = 350, lang: str = "kor+eng") -> pd.DataFrame:
    """Render a page to high‑DPI PNG and return a DataFrame of word boxes."""

    zoom = dpi / 72
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes("png")))
    
    df = pytesseract.image_to_data(
        img,
        lang=lang,
        config="--oem 3 --psm 3 -c preserve_interword_spaces=1",
        output_type=pytesseract.Output.DATAFRAME
    )
    df = df[(df.conf != -1) & df.text.notnull()].copy()
    df.rename(columns={"left": "x0", "top": "y0"}, inplace=True)
    df["x1"] = df.x0 + df.width
    df["y1"] = df.y0 + df.height
    return df[["x0", "y0", "x1", "y1", "text"]]

def is_multicol(df: pd.DataFrame, page_width: float, gap_ratio_thr: float = 0.15) -> bool:
    """Return True if the page likely has multiple text columns."""
    if len(df) < 30:
        return False
    centers = ((df.x0 + df.x1) / 2).to_numpy()
    centers.sort()
    gaps = np.diff(centers)
    return (gaps.max() / page_width) > gap_ratio_thr

def assign_columns_kmeans(df: pd.DataFrame, max_cols: int = 3) -> pd.DataFrame:
    """Cluster words into columns using 1‑D KMeans and label them."""
    k = min(max_cols, len(df))
    km = KMeans(n_clusters=k, n_init="auto").fit(
        ((df.x0 + df.x1) / 2).to_numpy().reshape(-1, 1)
    )
    df["col"] = km.labels_
    order = df.groupby("col").x0.min().sort_values().index.tolist()
    df["col"] = df.col.map({old: new for new, old in enumerate(order)})
    return df

def rebuild_text_from_columns(df: pd.DataFrame, line_tol: int = 8) -> str:
    """Reconstruct reading order: left‑to‑right columns, then top‑to‑bottom."""
    lines = []
    for col in sorted(df.col.unique()):
        col_df = df[df.col == col].sort_values(["y0", "x0"])
        current, last_top = [], None
        for _, w in col_df.iterrows():
            if last_top is None or abs(w.y0 - last_top) <= line_tol:
                current.append(w.text)
            else:
                lines.append(" ".join(current))
                current = [w.text]
            last_top = w.y0
        if current:
            lines.append(" ".join(current))
    return "\n".join(lines)

def extract_pdf_content(pdf_path: str,
                       ocr_lang: str = "kor+eng",
                       fast_mode: bool = False,
                       ocr_dpi: int = 350) -> Dict[str, Any]:
    """Extract text from a PDF with optional OCR and column reordering."""
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    pages_text: List[str] = []

    for i in range(total_pages):
        page = doc[i]
        raw_text = page.get_text("text").strip()

        # Build a DataFrame of word boxes
        if raw_text:
            words = page.get_text("words")
            words_df = pd.DataFrame(
                words,
                columns=["x0", "y0", "x1", "y1", "text", "_b", "_l", "_w"]
            )[["x0", "y0", "x1", "y1", "text"]]
        else:
            words_df = ocr_page_words(page, dpi=ocr_dpi, lang=ocr_lang)

        # Determine layout and rebuild text accordingly
        if is_multicol(words_df, page.rect.width):
            words_df = assign_columns_kmeans(words_df, max_cols=3)
            page_text = rebuild_text_from_columns(words_df)
        else:
            page_text = " ".join(
                w.text for _, w in
                words_df.sort_values(["y0", "x0"]).iterrows()
            )
        pages_text.append(page_text)

    sections = build_sections_from_layout(pages_text, fast_mode=fast_mode)
    
    return {
        "file_path": pdf_path,
        "pages_text": pages_text,
        "sections": sections
    }

def save_extracted_content(content: Dict[str, Any], output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(content, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    # Directory for original PDFs (e.g., data/original)
    pdf_folder = os.path.join("data", "original")
    output_folder = os.path.join("data", "extracted")
    os.makedirs(output_folder, exist_ok=True)

    pdf_files = [f for f in os.listdir(pdf_folder) if f.lower().endswith(".pdf")]
    if not pdf_files:
        print(f"[ERROR] No PDF files found in '{pdf_folder}'.")
        sys.exit(1)

    # If multiple PDFs exist, show the list and let the user choose
    if len(pdf_files) > 1:
        print("Multiple PDF files found:")
        for idx, fname in enumerate(pdf_files):
            print(f"{idx+1}. {fname}")
        selection = input("Select a file by number: ")
        try:
            selection_idx = int(selection) - 1
            if selection_idx < 0 or selection_idx >= len(pdf_files):
                print("Invalid selection.")
                sys.exit(1)
            selected_file = pdf_files[selection_idx]
        except ValueError:
            print("Invalid input.")
            sys.exit(1)
    else:
        selected_file = pdf_files[0]

    pdf_path = os.path.join(pdf_folder, selected_file)
    print(f"Processing file: {selected_file}")
    extracted_data = extract_pdf_content(pdf_path)

    base_name = os.path.splitext(selected_file)[0]
    output_json = os.path.join(output_folder, f"{base_name}.json")
    save_extracted_content(extracted_data, output_json)
    print(f"Processed {selected_file}: Found {len(extracted_data['sections'])} sections.")

    # Also save merged sections as sections.json for convenience
    sections_output = os.path.join(output_folder, "sections.json")
    with open(sections_output, 'w', encoding='utf-8') as f:
        json.dump(extracted_data["sections"], f, ensure_ascii=False, indent=2)
    print(f"Sections saved to {sections_output}")

    print("PDF Extraction Complete.")
