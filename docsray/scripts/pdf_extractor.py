#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import sys
import os
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT))

import fitz  # PyMuPDF
from typing import Dict, Any, List, Tuple, Optional
import io
from PIL import Image
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans

# Import FAST_MODE to determine if we can use image recognition
from docsray.config import FAST_MODE, MAX_TOKENS, FULL_FEATURE_MODE, USE_TESSERACT

if USE_TESSERACT:
    import pytesseract

# LLM for outline generation and image analysis
from docsray.inference.llm_model import local_llm, local_llm_large

from docsray.scripts.file_converter import FileConverter
from pathlib import Path

def extract_content(file_path: str,
                   analyze_visuals: bool = True,
                   visual_analysis_interval: int = 1,
                   auto_convert: bool = True,
                   page_limit: int=-1) -> Dict[str, Any]:
    """
    Extract text from a document file with optional visual content analysis using LLM.
    Automatically converts non-PDF files to PDF if auto_convert is True.
    
    Parameters:
    -----------
    file_path : str
        Path to the document file (PDF or other supported format)
    auto_convert : bool
        Whether to automatically convert non-PDF files to PDF
    """
    input_path = Path(file_path)
    
    # Check if file exists
    if not input_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")
    
    # Determine if conversion is needed
    is_pdf = input_path.suffix.lower() == '.pdf'
    
    if not is_pdf and auto_convert:
        print(f"📄 File is not PDF. Attempting to convert {input_path.suffix} to PDF...", file=sys.stderr)
        
        # Create converter
        converter = FileConverter()
        
        # Check if format is supported
        if not converter.is_supported(file_path):
            raise ValueError(f"Unsupported file format: {input_path.suffix}")
        
        # Convert to PDF
        success, result = converter.convert_to_pdf(file_path)
        
        if not success:
            raise RuntimeError(f"Failed to convert file: {result}")
        
        print(f"✅ Conversion successful: {result}", file=sys.stderr)
        pdf_path = result
        
        # Flag to clean up temporary file later
        temp_pdf = True
    else:
        pdf_path = file_path
        temp_pdf = False
    
    try:
        # Call original extract_pdf_content function
        result = extract_pdf_content(pdf_path, analyze_visuals, visual_analysis_interval, page_limit)
        
        # Update metadata to reflect original file
        result["metadata"]["original_file"] = str(input_path)
        result["metadata"]["was_converted"] = not is_pdf
        if not is_pdf:
            result["metadata"]["original_format"] = input_path.suffix.lower()
        
        return result
        
    finally:
        # Clean up temporary PDF if created
        if temp_pdf and os.path.exists(pdf_path):
            try:
                os.unlink(pdf_path)
                print(f"🗑️  Cleaned up temporary PDF", file=sys.stderr)
            except Exception as e:
                print(f"⚠️  Failed to clean up temporary PDF: {e}", file=sys.stderr)


# Alias for backward compatibility
extract_document_content = extract_content

def extract_images_from_page(page, min_width: int = 100, min_height: int = 100) -> List[Tuple[Image.Image, fitz.Rect]]:
    """
    Extract images from a PDF page that meet minimum size requirements.
    Returns list of (PIL Image, position rectangle) tuples.
    """
    images = []
    image_list = page.get_images()
    
    for img_index, img in enumerate(image_list):
        # Get image xref
        xref = img[0]
        
        # Extract image
        pix = fitz.Pixmap(page.parent, xref)
        pil_img = Image.open(io.BytesIO(pix.pil_tobytes(format="PNG")))
        
        # Check size
        if pil_img.width >= min_width and pil_img.height >= min_height:
            # Get image position on page
            img_rects = page.get_image_rects(xref)
            if img_rects:
                images.append((pil_img, img_rects[0]))

    images.sort(key=lambda x: (x[1].y0, x[1].x0))
    images = [img for img, rect in images]   

    return images


def analyze_image_with_llm(images: list, page_num: int) -> str:
    """
    Use multimodal LLM to analyze and describe an image.
    """
    
    # Prepare multimodal prompt
    prompt = """Describe all images in left-to-right, top-to-bottom order:

    Figure 1: [description]
    Figure 2: [description]
    Figure N: [description]

Start immediately with "Figure 1: ". No introduction needed."""
    # Use the large model for better image understanding
    response = local_llm_large.generate(prompt, images=images)
    
    return f"\n\n[{page_num + 1}]\n\n{response}\n\n"

def ocr_with_llm(image: Image.Image, page_num: int) -> str:
    """
    Use multimodal LLM for OCR instead of pytesseract.
    """
    
    # OCR-specific prompt
    prompt = """Extract text from this image and present it as readable paragraphs. Start directly with the content."""

    response = local_llm_large.generate(prompt, images=[image])
    extracted_text = local_llm_large.strip_response(response)
    return extracted_text.strip()

def analyze_visual_content(page, page_num: int) -> str:
    """
    Analyze visual content (images, charts, tables) on a page using multimodal LLM.
    """
    visual_graphics = []
    visual_description = ""
    
    # Extract images
    images = extract_images_from_page(page)

    if images:
        print(f"  Found {len(images)} images on page {page_num + 1}", file=sys.stderr)
        visual_graphics += images
    drawings = page.get_drawings()
    if drawings:
        # Count different types of drawing elements
        lines = sum(1 for d in drawings if d["type"] == "l")
        curves = sum(1 for d in drawings if d["type"] == "c")
        rects = sum(1 for d in drawings if d["type"] == "r")
        
        if lines > 10 or curves > 5 or rects > 5:
            # For complex vector graphics, render the page area as image and analyze
            # Get the bounding box of all drawings
            all_rects = [fitz.Rect(d["rect"]) for d in drawings]
            if all_rects:
                # Union of all drawing rectangles
                bbox = all_rects[0]
                for r in all_rects[1:]:
                    bbox = bbox | r  # Union operation
                
                # Render the area as image
                mat = fitz.Matrix(2, 2)  # 2x zoom for better quality
                pix = page.get_pixmap(matrix=mat, clip=bbox)
                vector_img = Image.open(io.BytesIO(pix.pil_tobytes(format="PNG")))
                visual_graphics.append(vector_img)
    if len(visual_graphics) > 0:
        visual_description += analyze_image_with_llm(visual_graphics, page_num)
    return visual_description


def build_sections_from_layout(pages_text: List[str],
                               init_chunk: int = 5,
                               min_pages: int = 3,
                               max_pages: int = 15) -> List[Dict[str, Any]]:
    """
Build pseudo‑TOC sections for a PDF lacking an explicit table of
contents.  Pipeline:
    1) Split pages into fixed blocks of `init_chunk` pages.
    2) For every proposed boundary, ask the local LLM whether the
        adjacent pages cover the same topic.  Merge blocks if so.
    3) For each final block, ask the LLM to propose a short title.
Returns a list of dicts identical in structure to build_sections_from_toc.
    """

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
            f"[Page A]\n{pages_text[a_idx][: (MAX_TOKENS - 100)//2]}\n\n"
            f"[Page B]\n{pages_text[a_idx+1][:(MAX_TOKENS - 100)//2]}\n\n"
        )
        try:
            resp = local_llm.generate(prompt).strip()
            resp = local_llm.strip_response(resp)

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
        sample_text = " ".join(pages_text[start:end])[: MAX_TOKENS - 100]  # leave space for LLM response
        title_prompt = prompt_template.format(sample=sample_text)
        try:
            title_line = local_llm_large.generate(title_prompt)
            title_line = local_llm_large.strip_response(title_line).strip()

        except Exception:
            title_line = f"Miscellaneous Section {start + 1}-{end}"

        sections.append({
            "title": title_line,
            "start_page": start + 1,  # 1‑based
            "end_page": end,
            "method": "LLM-Outline"
        })

    return sections

def ocr_page_with_llm(page, dpi: int = 350) -> str:
    """
    Render page to image and use LLM for OCR.
    Uses pytesseract if not in FULL_FEATURE_MODE.
    """

    # Render page to high-quality image
    zoom = dpi / 72
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    img = Image.open(io.BytesIO(pix.pil_tobytes(format="PNG")))
    
    if USE_TESSERACT:
        text = pytesseract.image_to_string(img)
    else:
        text = ocr_with_llm(img, page.number)         
     

    return text.strip()
      
    
def extract_text_blocks_for_layout(page) -> pd.DataFrame:
    """
    Extract text blocks with positions for layout analysis.
    Used when we have text but need to detect multi-column layout.
    """
    words = page.get_text("words")
    if not words:
        return pd.DataFrame(columns=["x0", "y0", "x1", "y1", "text"])
    
    df = pd.DataFrame(
        words,
        columns=["x0", "y0", "x1", "y1", "text", "_b", "_l", "_w"]
    )[["x0", "y0", "x1", "y1", "text"]]
    return df

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
                       analyze_visuals: bool = True,
                       visual_analysis_interval: int = 1,
                       page_limit: int=-1) -> Dict[str, Any]:
    """
    Extract text from a PDF with optional visual content analysis using LLM.
    
    Parameters:
    -----------
    pdf_path : str
        Path to the PDF file
    """


    doc = fitz.open(pdf_path)
    if page_limit != -1:
        doc = doc[:page_limit]
    total_pages = len(doc)
    pages_text: List[str] = []

    print(f"Extracting content from {total_pages} pages...", file=sys.stderr)
    if analyze_visuals:
        print(f"Visual analysis enabled (every {visual_analysis_interval} pages)", file=sys.stderr)

    for i in range(total_pages):
        page = doc[i]
        raw_text = page.get_text("text").strip()

        # Try to get text with layout information
        if raw_text:
            # Extract word positions for layout analysis
            words_df = extract_text_blocks_for_layout(page)
            
            # Check if multi-column layout
            if words_df.empty:
                page_text = raw_text
            elif is_multicol(words_df, page.rect.width):
                words_df = assign_columns_kmeans(words_df, max_cols=3)
                page_text = rebuild_text_from_columns(words_df)
            else:
                # Single column - use position-based ordering
                page_text = " ".join(
                    w.text for _, w in
                    words_df.sort_values(["y0", "x0"]).iterrows()
                )
        else:
            print(f"  Page {i+1}: No text found, performing OCR...", file=sys.stderr)
            page_text = ocr_page_with_llm(page)
    
        # Analyze visual content if enabled
        if analyze_visuals and (i % visual_analysis_interval == 0):
            print(f"  Analyzing visual content on page {i+1}...", file=sys.stderr)
            visual_content = analyze_visual_content(page, i)
            
            if visual_content:
                page_text += visual_content
        
        pages_text.append(page_text)
        
        # Progress indicator
        if (i + 1) % 10 == 0:
            print(f"  Processed {i + 1}/{total_pages} pages...", file=sys.stderr)

    print("Building document structure...", file=sys.stderr)
    sections = build_sections_from_layout(pages_text)
    
    return {
        "file_path": pdf_path,
        "pages_text": pages_text,
        "sections": sections,
        "metadata": {
            "total_pages": total_pages,
            "visual_analysis": analyze_visuals,
            "visual_analysis_interval": visual_analysis_interval if analyze_visuals else None,
            "fast_mode": FAST_MODE
        }
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
    
    # Ask user about visual analysis options
    analyze_visuals = input("Analyze visual content (images, charts)? (y/N): ").lower() == 'y'
    
    visual_interval = 1
    if analyze_visuals:
        interval_input = input("Analyze visuals every N pages (default 1): ").strip()
        if interval_input.isdigit():
            visual_interval = int(interval_input)
    
    extracted_data = extract_pdf_content(
        pdf_path, 
        analyze_visuals=analyze_visuals,
        visual_analysis_interval=visual_interval
    )

    base_name = os.path.splitext(selected_file)[0]
    output_json = os.path.join(output_folder, f"{base_name}.json")
    save_extracted_content(extracted_data, output_json)
    
    print(f"\nProcessing complete!")
    print(f"- Document: {selected_file}")
    print(f"- Sections found: {len(extracted_data['sections'])}")
    print(f"- Total pages: {extracted_data['metadata']['total_pages']}")
    print(f"- Fast mode: {extracted_data['metadata']['fast_mode']}")
    if analyze_visuals:
        print(f"- Visual analysis: Every {visual_interval} pages")

    # Also save merged sections as sections.json for convenience
    sections_output = os.path.join(output_folder, "sections.json")
    with open(sections_output, 'w', encoding='utf-8') as f:
        json.dump(extracted_data["sections"], f, ensure_ascii=False, indent=2)
    print(f"\nSections saved to {sections_output}")

    print("\nPDF Extraction Complete.")