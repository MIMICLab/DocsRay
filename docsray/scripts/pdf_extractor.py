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

def is_vector_component_image(pil_img: Image.Image, page_rect: fitz.Rect) -> bool:
    """
    Determine if an image is likely a component of vector graphics rather than a standalone image.
    """
    # Very small images are likely vector components
    if pil_img.width < 50 or pil_img.height < 50:
        return True
    
    # Images that are mostly one color (like fills or simple shapes)
    try:
        # Convert to RGB if needed
        if pil_img.mode != 'RGB':
            img_rgb = pil_img.convert('RGB')
        else:
            img_rgb = pil_img
        
        # Sample pixels to check color diversity
        import random
        pixels = []
        width, height = img_rgb.size
        sample_size = min(100, width * height // 10)  # Sample up to 100 pixels
        
        for _ in range(sample_size):
            x = random.randint(0, width - 1)
            y = random.randint(0, height - 1)
            pixels.append(img_rgb.getpixel((x, y)))
        
        # Check color diversity
        unique_colors = set(pixels)
        color_diversity = len(unique_colors) / len(pixels)
        
        # If very low color diversity, likely a vector component
        if color_diversity < 0.1:  # Less than 10% unique colors
            return True
            
        # Check if it's mostly white/transparent (common in vector graphics)
        white_count = sum(1 for r, g, b in pixels if r > 240 and g > 240 and b > 240)
        if white_count / len(pixels) > 0.8:  # More than 80% white
            return True
            
    except Exception:
        # If color analysis fails, fall back to size-based decision
        pass
    
    # Check aspect ratio - very thin images might be lines or borders
    aspect_ratio = max(pil_img.width, pil_img.height) / min(pil_img.width, pil_img.height)
    if aspect_ratio > 10:  # Very elongated
        return True
    
    return False

def extract_images_from_page(page, min_width: int = 100, min_height: int = 100, filter_vector_components: bool = False) -> List[Image.Image]:
    """
    Extract images from a PDF page that meet minimum size requirements.
    Returns list of PIL Images sorted by position.
    """
    images = []
    
    try:
        image_list = page.get_images()
    except Exception as e:
        print(f"⚠️  Failed to get images from page {page.number + 1}: {e}", file=sys.stderr)
        return images
    
    image_positions = []  # Store (image, rect) for sorting
    
    for img_index, img in enumerate(image_list):
        # Get image xref
        xref = img[0]
        pix = None
        
        try:
            # Extract image with better error handling
            pix = fitz.Pixmap(page.parent, xref)
            
            # Check if pixmap is valid
            if pix.width == 0 or pix.height == 0:
                continue
                
            # Convert to PIL Image
            if pix.n - pix.alpha < 4:  # GRAY or RGB
                pil_img = Image.open(io.BytesIO(pix.pil_tobytes(format="PNG")))
            else:  # CMYK: convert to RGB first
                pix_rgb = fitz.Pixmap(fitz.csRGB, pix)
                pil_img = Image.open(io.BytesIO(pix_rgb.pil_tobytes(format="PNG")))
                pix_rgb = None  # Clean up immediately
            
            # Check size requirements
            if pil_img.width >= min_width and pil_img.height >= min_height:
                # Additional filtering for vector components if requested
                if filter_vector_components and is_vector_component_image(pil_img, page.rect):
                    print(f"    Filtered out vector component image {img_index} ({pil_img.width}x{pil_img.height})", file=sys.stderr)
                    pil_img.close()
                    continue
                
                # Get image position on page
                try:
                    img_rects = page.get_image_rects(xref)
                    if img_rects:
                        image_positions.append((pil_img, img_rects[0]))
                    else:
                        # If no position info, add to end
                        image_positions.append((pil_img, fitz.Rect(999, 999, 999, 999)))
                except Exception as e:
                    print(f"⚠️  Failed to get image position for image {img_index}: {e}", file=sys.stderr)
                    # Add image without position info
                    image_positions.append((pil_img, fitz.Rect(999, 999, 999, 999)))
            else:
                # Image too small, close it
                pil_img.close()
                
        except Exception as e:
            print(f"⚠️  Failed to extract image {img_index} from page {page.number + 1}: {e}", file=sys.stderr)
            continue
        finally:
            # Clean up pixmap
            if pix:
                pix = None
    
    # Sort images by position (top-to-bottom, left-to-right)
    image_positions.sort(key=lambda x: (x[1].y0, x[1].x0))
    images = [img for img, rect in image_positions]
    
    return images


def analyze_image_with_llm(images: list, page_num: int) -> str:
    """
    Use multimodal LLM to analyze and describe images.
    """
    if not images:
        return ""
    
    # Different prompts based on number of images
    if len(images) == 1:
        prompt = """Describe this visual content. If it's a chart, graph, or diagram, explain what data or information it shows. If it's a photo or illustration, describe what it depicts. Be concise but informative."""
    else:
        prompt = f"""Describe these {len(images)} visual elements in order:

Figure 1: [description]
Figure 2: [description]
Figure N: [description]

For each figure, identify if it's a chart/graph/diagram (and what data it shows) or a photo/illustration (and what it depicts). Start immediately with "Figure 1:"."""
    
    try:
        # Use the large model for better image understanding
        response = local_llm.generate(prompt, images=images)
        
        # Clean up the response
        cleaned_response = local_llm.strip_response(response)
        
        return f"\n\n[Visual Content - Page {page_num + 1}]\n{cleaned_response}\n\n"
        
    except Exception as e:
        print(f"⚠️  LLM analysis failed for page {page_num + 1}: {e}", file=sys.stderr)
        return f"\n\n[Visual Content - Page {page_num + 1}]\n[{len(images)} visual element(s) found but analysis failed]\n\n"

def ocr_with_llm(image: Image.Image, page_num: int) -> str:
    """
    Use multimodal LLM for OCR instead of pytesseract.
    """
    
    # OCR-specific prompt
    prompt = """Extract text from this image and present it as readable paragraphs. Start directly with the content."""

    response = local_llm.generate(prompt, images=[image])
    extracted_text = local_llm.strip_response(response)
    return extracted_text.strip()

def detect_tables(page) -> List[fitz.Rect]:
    """
    Detect table structures on a page using text alignment patterns.
    """
    tables = []
    
    try:
        # Get text blocks with position information
        text_dict = page.get_text("dict")
        
        # Extract lines from blocks
        all_lines = []
        for block in text_dict["blocks"]:
            if "lines" in block:
                for line in block["lines"]:
                    bbox = fitz.Rect(line["bbox"])
                    text = ""
                    for span in line["spans"]:
                        text += span["text"] + " "
                    if text.strip():
                        all_lines.append({
                            "bbox": bbox,
                            "text": text.strip(),
                            "y": bbox.y0
                        })
        
        if len(all_lines) < 3:
            return tables
        
        # Group lines by approximate Y position (rows)
        all_lines.sort(key=lambda x: x["y"])
        rows = []
        current_row = []
        current_y = None
        tolerance = 5  # pixels
        
        for line in all_lines:
            if current_y is None or abs(line["y"] - current_y) <= tolerance:
                current_row.append(line)
                current_y = line["y"] if current_y is None else current_y
            else:
                if len(current_row) >= 2:  # At least 2 columns
                    rows.append(current_row)
                current_row = [line]
                current_y = line["y"]
        
        if len(current_row) >= 2:
            rows.append(current_row)
        
        # Look for table patterns (at least 3 rows with similar column structure)
        if len(rows) >= 3:
            # Find consistent column positions
            column_positions = []
            for row in rows[:5]:  # Check first 5 rows
                positions = sorted([line["bbox"].x0 for line in row])
                column_positions.append(positions)
            
            # Check if we have consistent column structure
            if len(set(len(pos) for pos in column_positions)) == 1:  # Same number of columns
                # Calculate table bounding box
                min_x = min(min(line["bbox"].x0 for line in row) for row in rows)
                max_x = max(max(line["bbox"].x1 for line in row) for row in rows)
                min_y = min(min(line["bbox"].y0 for line in row) for row in rows)
                max_y = max(max(line["bbox"].y1 for line in row) for row in rows)
                
                table_rect = fitz.Rect(min_x - 5, min_y - 5, max_x + 5, max_y + 5)
                
                # Ensure minimum table size
                if table_rect.width > 100 and table_rect.height > 50:
                    tables.append(table_rect)
                    print(f"  Detected table: {table_rect.width:.0f}x{table_rect.height:.0f} with {len(rows)} rows", file=sys.stderr)
        
    except Exception as e:
        print(f"⚠️  Table detection failed: {e}", file=sys.stderr)
    
    return tables

def analyze_visual_content(page, page_num: int) -> str:
    """
    Analyze visual content (images, charts, tables) on a page using multimodal LLM.
    """
    visual_graphics = []
    visual_description = ""
    
    # First, detect and capture tables
    try:
        tables = detect_tables(page)
        for table_rect in tables:
            try:
                # Render table area as image
                zoom = min(2.0, 800 / max(table_rect.width, table_rect.height))
                mat = fitz.Matrix(zoom, zoom)
                pix = page.get_pixmap(matrix=mat, clip=table_rect, alpha=False)
                
                if pix.width > 0 and pix.height > 0:
                    table_img = Image.open(io.BytesIO(pix.pil_tobytes(format="PNG")))
                    visual_graphics.append(table_img)
                    print(f"  Captured table as image on page {page_num + 1}", file=sys.stderr)
                    pix = None  # Clean up immediately
                    
            except Exception as e:
                print(f"⚠️  Failed to capture table on page {page_num + 1}: {e}", file=sys.stderr)
                
    except Exception as e:
        print(f"⚠️  Table detection failed on page {page_num + 1}: {e}", file=sys.stderr)
    
    # Then, analyze vector graphics to understand the drawing structure
    vector_img = None
    has_complex_vectors = False
    
    try:
        drawings = page.get_drawings()
        
        if drawings:
            # Count different types of drawing elements
            # PyMuPDF returns drawing types as "f" (fill), "s" (stroke), "fs" (fill+stroke)
            # We need to look at the items within each drawing to count lines, curves, rects
            lines = 0
            curves = 0
            rects = 0
            
            for drawing in drawings:
                items = drawing.get("items", [])
                for item in items:
                    if isinstance(item, tuple) and len(item) >= 2:
                        cmd = item[0]
                        if cmd == "l":  # line
                            lines += 1
                        elif cmd == "c":  # curve
                            curves += 1
                        elif cmd == "re":  # rectangle
                            rects += 1
            
            # Debug: print drawing details if any drawings exist
            total_drawings = len(drawings)
            if total_drawings > 0:
                print(f"  Detected {total_drawings} drawing paths on page {page_num + 1} (lines: {lines}, curves: {curves}, rects: {rects})", file=sys.stderr)
            
            # Only analyze complex drawings to avoid processing simple borders
            # Also check that we actually found some drawing commands
            total_commands = lines + curves + rects
            if total_commands > 0 and (lines > 15 or curves > 8 or rects > 8):
                has_complex_vectors = True
                print(f"  Processing as complex vector graphics", file=sys.stderr)
            elif total_drawings > 10:  # Many paths but few drawing commands - still might be complex
                # Check if we have many paths with fills/strokes that could be vector graphics
                has_complex_vectors = True
                print(f"  Processing as complex vector graphics (many paths detected)", file=sys.stderr)
                
                # Get the bounding box of all drawings
                try:
                    all_rects = []
                    for d in drawings:
                        if "rect" in d and d["rect"]:
                            all_rects.append(fitz.Rect(d["rect"]))
                    
                    if all_rects:
                        # Union of all drawing rectangles
                        bbox = all_rects[0]
                        for r in all_rects[1:]:
                            bbox = bbox | r  # Union operation
                        
                        # Only render if bbox is reasonable size
                        if bbox.width > 50 and bbox.height > 50:
                            print(f"  Rendered vector graphics area: {int(bbox.width)}x{int(bbox.height)} pixels", file=sys.stderr)
                            # Calculate appropriate zoom
                            max_dimension = max(bbox.width, bbox.height)
                            zoom = min(2.0, 800 / max_dimension) if max_dimension > 0 else 1.0
                            
                            mat = fitz.Matrix(zoom, zoom)
                            pix = page.get_pixmap(matrix=mat, clip=bbox, alpha=False)
                            
                            if pix.width > 0 and pix.height > 0:
                                vector_img = Image.open(io.BytesIO(pix.pil_tobytes(format="PNG")))
                                visual_graphics.append(vector_img)
                                pix = None  # Clean up immediately
                                
                except Exception as e:
                    print(f"⚠️  Failed to render drawings as image on page {page_num + 1}: {e}", file=sys.stderr)
                    
    except Exception as e:
        print(f"⚠️  Failed to get drawings from page {page_num + 1}: {e}", file=sys.stderr)
    
    # Extract standalone images (but filter out vector graphic components if complex vectors exist)
    try:
        if has_complex_vectors:
            # When complex vectors exist, be very selective about images to avoid duplicates
            print(f"  Using strict filtering to avoid vector component images", file=sys.stderr)
            images = extract_images_from_page(page, min_width=120, min_height=120, filter_vector_components=True)
            
            # Additional size-based filtering for very complex vector pages
            filtered_images = []
            for img in images:
                # Only include images that are significantly large and likely to be standalone content
                pixel_count = img.width * img.height
                if pixel_count > 30000:  # Minimum 30k pixels (e.g., 200x150)
                    # Check if image area is reasonable compared to page
                    try:
                        img_rects = page.get_image_rects(img)  # This might not work, but try
                        # If we can't get rect info, include the image anyway
                        filtered_images.append(img)
                    except:
                        # Include image if we can't determine position
                        filtered_images.append(img)
                else:
                    img.close()  # Clean up small images
            images = filtered_images
        else:
            # No complex vectors, extract all reasonable-sized images with light filtering
            images = extract_images_from_page(page, min_width=100, min_height=100, filter_vector_components=True)
        
        if images:
            print(f"  Found {len(images)} standalone images on page {page_num + 1}", file=sys.stderr)
            visual_graphics.extend(images)
        else:
            print(f"  No standalone images found on page {page_num + 1}", file=sys.stderr)
            
    except Exception as e:
        print(f"⚠️  Failed to extract images from page {page_num + 1}: {e}", file=sys.stderr)
    
    # Analyze all visual content if any found
    if visual_graphics:
        try:
            # Sort by type: vector graphics first, then images
            vector_graphics = [vector_img] if vector_img else []
            standalone_images = [img for img in visual_graphics if img != vector_img]
            
            # Analyze in order: charts/diagrams first, then photos/images
            ordered_graphics = vector_graphics + standalone_images
            
            visual_description = analyze_image_with_llm(ordered_graphics, page_num)
        except Exception as e:
            print(f"⚠️  Failed to analyze visual content on page {page_num + 1}: {e}", file=sys.stderr)
            visual_description = f"\n\n[Page: {page_num + 1}]\n[Visual content found but analysis failed]\n\n"
        finally:
            # Clean up images to free memory
            for img in visual_graphics:
                if hasattr(img, 'close'):
                    img.close()
    
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
    pix = None
    img = None
    
    try:
        # Check if page has embedded text
        try:
            has_text = bool(page.get_text("text").strip())
        except Exception:
            has_text = False

        # Choose appropriate DPI
        dpi = dpi_fast if has_text else (dpi_scan if page.rect.width < 600 else dpi_fast)
        zoom = dpi / 72
        
        # Limit zoom to prevent excessive memory usage
        zoom = min(zoom, 4.0)  # Max 4x zoom

        # Render page to image
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        
        # Check if pixmap is valid
        if pix.width == 0 or pix.height == 0:
            return ""
            
        # Convert to PIL Image
        img = Image.open(io.BytesIO(pix.pil_tobytes(format="PNG")))
        
        # Perform OCR
        if USE_TESSERACT:
            try:
                text = pytesseract.image_to_string(img, config='--oem 3 --psm 6')
            except Exception as e:
                print(f"⚠️  Tesseract OCR failed on page {page.number + 1}: {e}", file=sys.stderr)
                # Fallback to LLM OCR
                text = ocr_with_llm(img, page.number)
        else:
            text = ocr_with_llm(img, page.number)
            
        return text.strip() if text else ""
        
    except Exception as e:
        print(f"⚠️  Failed to render page {page.number + 1} for OCR: {e}", file=sys.stderr)
        return ""
    finally:
        # Clean up resources
        if img:
            img.close()
        if pix:
            pix = None
      
    
def extract_text_blocks_for_layout(page) -> pd.DataFrame:
    """
    Extract text blocks with positions for layout analysis.
    Used when we have text but need to detect multi-column layout.
    """
    try:
        words = page.get_text("words")
    except Exception as e:
        print(f"⚠️  Failed to extract text blocks from page {page.number + 1}: {e}", file=sys.stderr)
        return pd.DataFrame(columns=["x0", "y0", "x1", "y1", "text"])
    
    if not words:
        return pd.DataFrame(columns=["x0", "y0", "x1", "y1", "text"])
    
    try:
        # Handle different word tuple lengths (PyMuPDF versions may vary)
        if len(words) > 0:
            first_word = words[0]
            if len(first_word) >= 5:
                # Standard format: (x0, y0, x1, y1, text, block_no, line_no, word_no)
                df = pd.DataFrame(
                    words,
                    columns=["x0", "y0", "x1", "y1", "text", "_b", "_l", "_w"]
                )[["x0", "y0", "x1", "y1", "text"]]
            else:
                # Minimal format: (x0, y0, x1, y1, text)
                df = pd.DataFrame(
                    words,
                    columns=["x0", "y0", "x1", "y1", "text"]
                )
        else:
            return pd.DataFrame(columns=["x0", "y0", "x1", "y1", "text"])
        
        # Filter out empty text
        df = df[df['text'].str.strip() != '']
        
        return df
        
    except Exception as e:
        print(f"⚠️  Failed to process text blocks from page {page.number + 1}: {e}", file=sys.stderr)
        return pd.DataFrame(columns=["x0", "y0", "x1", "y1", "text"])

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
        page = None
        page_text = ""
        
        try:
            page = doc[i]
        except Exception as e:
            print(f"⚠️  Failed to access page {i+1}: {e}", file=sys.stderr)
            pages_text.append("")
            continue
        
        try:
            # Extract raw text
            try:
                raw_text = page.get_text("text").strip()
            except Exception as e:
                print(f"⚠️  Failed to extract text from page {i+1}: {e}", file=sys.stderr)
                raw_text = ""

            # Process text with layout analysis if available
            if raw_text:
                try:
                    # Extract word positions for layout analysis
                    words_df = extract_text_blocks_for_layout(page)
                    
                    # Check if multi-column layout
                    if words_df.empty:
                        page_text = raw_text
                    elif len(words_df) > 10 and is_multicol(words_df, page.rect.width):
                        # Multi-column layout detected
                        try:
                            words_df = assign_columns_kmeans(words_df, max_cols=3)
                            page_text = rebuild_text_from_columns(words_df)
                        except Exception as e:
                            print(f"⚠️  Multi-column processing failed on page {i+1}: {e}", file=sys.stderr)
                            page_text = raw_text  # Fallback to raw text
                    else:
                        # Single column - use position-based ordering
                        try:
                            page_text = " ".join(
                                w.text for _, w in
                                words_df.sort_values(["y0", "x0"]).iterrows()
                            )
                        except Exception as e:
                            print(f"⚠️  Position-based text ordering failed on page {i+1}: {e}", file=sys.stderr)
                            page_text = raw_text  # Fallback to raw text
                            
                except Exception as e:
                    print(f"⚠️  Layout analysis failed on page {i+1}: {e}", file=sys.stderr)
                    page_text = raw_text  # Fallback to raw text
            else:
                # No embedded text found, perform OCR
                print(f"  Page {i+1}: No embedded text found, performing OCR...", file=sys.stderr)
                try:
                    page_text = ocr_page_with_llm(page)
                    if not page_text.strip():
                        print(f"  Page {i+1}: OCR produced no text", file=sys.stderr)
                except Exception as e:
                    print(f"⚠️  OCR failed on page {i+1}: {e}", file=sys.stderr)
                    page_text = ""
        
            # Analyze visual content if enabled
            if analyze_visuals and (i % visual_analysis_interval == 0):
                print(f"  Analyzing visual content on page {i+1}...", file=sys.stderr)
                try:
                    visual_content = analyze_visual_content(page, i)
                    if visual_content:
                        page_text += visual_content
                except Exception as e:
                    print(f"⚠️  Visual analysis failed on page {i+1}: {e}", file=sys.stderr)
        
        except Exception as e:
            print(f"⚠️  Page processing failed on page {i+1}: {e}", file=sys.stderr)
            page_text = ""
        
        finally:
            # Always append the result (even if empty)
            pages_text.append(page_text)
            
            # Clean up page resources
            if page:
                page = None
                
            # More frequent garbage collection and memory management
            if (i + 1) % 3 == 0:
                gc.collect()
                
            # Progress indicator
            if (i + 1) % 5 == 0:
                print(f"  Processed {i + 1}/{total_pages} pages...", file=sys.stderr)

    print("Building document structure...", file=sys.stderr)
    
    try:
        sections = build_sections_from_layout(pages_text)
    except Exception as e:
        print(f"⚠️  Failed to build document structure: {e}", file=sys.stderr)
        # Create a simple fallback section
        sections = [{
            "title": "Full Document",
            "start_page": 1,
            "end_page": total_pages,
            "method": "Fallback"
        }]
    
    # Clean up document resources
    try:
        doc.close()
    except Exception as e:
        print(f"⚠️  Failed to close PDF document: {e}", file=sys.stderr)
    
    # Final garbage collection
    gc.collect()
    
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
