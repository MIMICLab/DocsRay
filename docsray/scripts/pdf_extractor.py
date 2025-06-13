#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import sys
import os
import pathlib

import fitz  # PyMuPDF
from typing import Dict, Any, List, Tuple, Optional
import io
from PIL import Image
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
import gc  # garbage collection

# Import FAST_MODE to determine if we can use image recognition
from docsray.config import FAST_MODE, MAX_TOKENS, FULL_FEATURE_MODE, USE_TESSERACT

if USE_TESSERACT:
    import pytesseract

# LLM for outline generation and image analysis
from docsray.inference.llm_model import local_llm
from docsray.scripts.file_converter import FileConverter
from pathlib import Path

def extract_content(file_path: str,
                   analyze_visuals: bool = True,
                   visual_analysis_interval: int = 1,
                   auto_convert: bool = True,
                   page_limit: int=0) -> Dict[str, Any]:
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

def extract_images_from_page(page, min_width: int = 100, min_height: int = 100, min_area_ratio: float = 0.02) -> List[Tuple[Image.Image, fitz.Rect]]:
    """
    Extract images from a PDF page that meet minimum size requirements.
    Filters out small icons and UI elements.
    
    Args:
        page: PyMuPDF page object
        min_width: Minimum width in pixels
        min_height: Minimum height in pixels
        min_area_ratio: Minimum ratio of image area to page area
    
    Returns:
        List of PIL Image objects
    """
    images = []
    page_area = page.rect.width * page.rect.height
    
    try:
        image_list = page.get_images()
    except Exception as e:
        print(f"⚠️  Failed to get images from page: {e}", file=sys.stderr)
        return images
    
    for img_index, img in enumerate(image_list):
        # Get image xref
        xref = img[0]
        
        try:
            # Get image position on page first to check size
            img_rects = page.get_image_rects(xref)
            if not img_rects:
                continue
                
            rect = img_rects[0]
            rect_area = rect.width * rect.height
            
            # Skip if image takes up too little of the page (likely an icon)
            if rect_area / page_area < min_area_ratio:
                continue
            
            # Extract image
            pix = fitz.Pixmap(page.parent, xref)
            
            # Check pixel dimensions
            if pix.width < min_width or pix.height < min_height:
                continue
            
            # Check aspect ratio to filter out UI elements (very thin or tall images)
            aspect_ratio = pix.width / pix.height
            if aspect_ratio > 10 or aspect_ratio < 0.1:
                continue
            
            pil_img = Image.open(io.BytesIO(pix.pil_tobytes(format="PNG")))
            images.append((pil_img, rect))
            
        except Exception as e:
            print(f"⚠️  Failed to extract image {img_index}: {e}", file=sys.stderr)
            continue
    
    # Sort by position (top to bottom, left to right)
    images.sort(key=lambda x: (x[1].y0, x[1].x0))
    
    # Return only the images (without rectangles)
    return [img for img, rect in images]


def analyze_image_with_llm(images: list, page_num: int) -> str:
    """
    Use multimodal LLM to analyze and describe images.
    """
    
    # Prepare multimodal prompt based on content type
    prompt = """Describe all images in left-to-right, top-to-bottom order:

    Figure 1: [description]
    Figure 2: [description]
    Figure N: [description]

Start immediately with "Figure 1: ". No introduction needed."""
    
    response = local_llm.generate(prompt, images=images)
    
    return f"\n\n[Visual Content - Page {page_num + 1}]\n{response}\n\n"

def ocr_with_llm(image: Image.Image, page_num: int) -> str:
    """
    Use multimodal LLM for OCR instead of pytesseract.
    """
    
    # OCR-specific prompt
    prompt = """Extract text from this image and present it as readable paragraphs. Start directly with the content."""

    response = local_llm.generate(prompt, images=[image])
    extracted_text = local_llm.strip_response(response)
    return extracted_text.strip()

def analyze_visual_content(page, page_num: int) -> str:
    """
    Analyze visual content (images, charts, tables) on a page using multimodal LLM.
    First checks for vector graphics to avoid capturing embedded icons.
    """
    visual_graphics = []
    visual_description = ""
    has_complex_vector_graphics = False
    
    # First, check for vector graphics (drawings)
    try:
        drawings = page.get_drawings()
    except Exception as e:
        print(f"⚠️  Failed to get drawings from page {page_num + 1}: {e}", file=sys.stderr)
        drawings = []
    
    if drawings:
        # Count different types of drawing elements
        lines = sum(1 for d in drawings if d["type"] == "l")
        curves = sum(1 for d in drawings if d["type"] == "c")
        rects = sum(1 for d in drawings if d["type"] == "r")
        fills = sum(1 for d in drawings if d["type"] == "f")
        strokes = sum(1 for d in drawings if d["type"] == "s")
        
        # Total number of drawing elements
        total_drawings = len(drawings)
        
        # Check if this is a complex vector graphic (chart, diagram, etc.)
        # Need significant number of actual drawing operations, not just fills
        has_significant_paths = lines > 10 or curves > 5 or (lines + curves) > 8
        has_significant_shapes = rects > 10 or (rects > 5 and fills > 3)
        has_many_elements = total_drawings > 20
        
        if has_significant_paths or has_significant_shapes or has_many_elements:
            has_complex_vector_graphics = True
            print(f"  Detected complex vector graphics on page {page_num + 1} (lines: {lines}, curves: {curves}, rects: {rects}, fills: {fills}, total: {total_drawings})", file=sys.stderr)
            
            # For complex vector graphics, render the entire drawing area as one image
            all_rects = [fitz.Rect(d["rect"]) for d in drawings]
            if all_rects:
                # Union of all drawing rectangles
                bbox = all_rects[0]
                for r in all_rects[1:]:
                    bbox = bbox | r  # Union operation
                
                # Check if the bounding box is reasonable (not too small, not entire page)
                page_rect = page.rect
                bbox_area = bbox.width * bbox.height
                page_area = page_rect.width * page_rect.height
                
                # Only render if the graphics area is significant but not the entire page
                if bbox_area > 100 and bbox_area < page_area * 0.9:
                    # Expand bbox slightly to capture full graphics
                    bbox.x0 = max(bbox.x0 - 5, page_rect.x0)
                    bbox.y0 = max(bbox.y0 - 5, page_rect.y0)
                    bbox.x1 = min(bbox.x1 + 5, page_rect.x1)
                    bbox.y1 = min(bbox.y1 + 5, page_rect.y1)
                    
                    try:
                        # Render the area as image
                        zoom = min(2.0, 800 / max(bbox.width, bbox.height))
                        mat = fitz.Matrix(zoom, zoom)
                        pix = page.get_pixmap(matrix=mat, clip=bbox)
                        vector_img = Image.open(io.BytesIO(pix.pil_tobytes(format="PNG")))
                        visual_graphics.append(vector_img)
                        print(f"  Rendered vector graphics area: {bbox.width:.0f}x{bbox.height:.0f} pixels", file=sys.stderr)
                    except Exception as e:
                        print(f"⚠️  Failed to render drawings as image on page {page_num + 1}: {e}", file=sys.stderr)
                else:
                    # Graphics too small or covers entire page, treat as regular page
                    has_complex_vector_graphics = False
                    print(f"  Vector graphics area not suitable for separate rendering (area ratio: {bbox_area/page_area:.2f})", file=sys.stderr)
    
    # Extract individual images
    # If we have complex vector graphics, be more strict about image filtering
    if has_complex_vector_graphics:
        # Use stricter filtering for pages with vector graphics
        images = extract_images_from_page(page, min_width=150, min_height=150, min_area_ratio=0.05)
        if images:
            print(f"  Found {len(images)} significant images alongside vector graphics", file=sys.stderr)
            visual_graphics += images
    else:
        # Normal image extraction for pages without complex vector graphics
        images = extract_images_from_page(page)
        if images:
            print(f"  Found {len(images)} standalone images on page {page_num + 1}", file=sys.stderr)
            visual_graphics += images
    
    # Analyze all visual content together
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
            title_line = local_llm.generate(title_prompt)
            title_line = local_llm.strip_response(title_line).strip()

        except Exception:
            title_line = f"Miscellaneous Section {start + 1}-{end}"

        sections.append({
            "title": title_line,
            "start_page": start + 1,  # 1‑based
            "end_page": end,
            "method": "LLM-Outline"
        })

    return sections

def ocr_page_with_llm(page, dpi_fast: int = 150, dpi_scan: int = 300) -> str:
    """
    Render the page to an image and perform OCR.

    DPI selection:
      • embedded text exists → 150
      • else and page.width < 600 pt → 300
      • otherwise → 150
    """
    try:
        has_text = bool(page.get_text("text").strip())
    except Exception:
        has_text = False

    dpi = dpi_fast if has_text else (dpi_scan if page.rect.width < 600 else dpi_fast)
    zoom = dpi / 72

    try:
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        img = Image.open(io.BytesIO(pix.pil_tobytes(format="PNG")))
    except Exception as e:
        print(f"⚠️  Failed to render page {page.number + 1} for OCR: {e}", file=sys.stderr)
        return ""

    text = pytesseract.image_to_string(img) if USE_TESSERACT else ocr_with_llm(img, page.number)
    return text.strip()
      
    
def extract_text_blocks_for_layout(page) -> pd.DataFrame:
    """
    Extract text blocks with positions for layout analysis.
    Used when we have text but need to detect multi-column layout.
    """
    try:
        words = page.get_text("words")
    except Exception as e:
        print(f"⚠️  Failed to extract text blocks from page: {e}", file=sys.stderr)
        return pd.DataFrame(columns=["x0", "y0", "x1", "y1", "text"])
    
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
                       page_limit: int=0) -> Dict[str, Any]:
    """
    Extract text from a PDF with optional visual content analysis using LLM.
    
    Parameters:
    -----------
    pdf_path : str
        Path to the PDF file
    """

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"❌ Failed to open PDF file: {e}", file=sys.stderr)
        raise
    
    if page_limit > 0:
        doc = doc[:page_limit]
    total_pages = len(doc)
    pages_text: List[str] = []

    print(f"Extracting content from {total_pages} pages...", file=sys.stderr)
    if analyze_visuals:
        print(f"Visual analysis enabled (every {visual_analysis_interval} pages)", file=sys.stderr)

    for i in range(total_pages):
        try:
            page = doc[i]
        except Exception as e:
            print(f"⚠️  Failed to access page {i+1}: {e}", file=sys.stderr)
            pages_text.append("")
            continue
        
        try:
            raw_text = page.get_text("text").strip()
        except Exception as e:
            print(f"⚠️  Failed to extract text from page {i+1}: {e}", file=sys.stderr)
            raw_text = ""

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
        
        # Clean up any created image objects
        if 'page' in locals():
            del page
        gc.collect()
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
        print(f"[ERROR] No PDF files found in '{pdf_folder}'.", file=sys.stderr)
        sys.exit(1)

    # If multiple PDFs exist, show the list and let the user choose
    if len(pdf_files) > 1:
        print("Multiple PDF files found:", file=sys.stderr)
        for idx, fname in enumerate(pdf_files):
            print(f"{idx+1}. {fname}", file=sys.stderr)
        selection = input("Select a file by number: ")
        try:
            selection_idx = int(selection) - 1
            if selection_idx < 0 or selection_idx >= len(pdf_files):
                print("Invalid selection.", file=sys.stderr)
                sys.exit(1)
            selected_file = pdf_files[selection_idx]
        except ValueError:
            print("Invalid input.", file=sys.stderr)
            sys.exit(1)
    else:
        selected_file = pdf_files[0]

    pdf_path = os.path.join(pdf_folder, selected_file)
    print(f"Processing file: {selected_file}", file=sys.stderr)
    
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
    
    print(f"\nProcessing complete!", file=sys.stderr)
    print(f"- Document: {selected_file}", file=sys.stderr)
    print(f"- Sections found: {len(extracted_data['sections'])}", file=sys.stderr)
    print(f"- Total pages: {extracted_data['metadata']['total_pages']}", file=sys.stderr)
    print(f"- Fast mode: {extracted_data['metadata']['fast_mode']}", file=sys.stderr)
    if analyze_visuals:
        print(f"- Visual analysis: Every {visual_interval} pages", file=sys.stderr)

    # Also save merged sections as sections.json for convenience
    sections_output = os.path.join(output_folder, "sections.json")
    with open(sections_output, 'w', encoding='utf-8') as f:
        json.dump(extracted_data["sections"], f, ensure_ascii=False, indent=2)
    print(f"\nSections saved to {sections_output}", file=sys.stderr)

    print("\nPDF Extraction Complete.", file=sys.stderr)
