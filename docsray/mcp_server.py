#!/usr/bin/env python3
# mcp_server.py - Enhanced version with document summarization

"""Enhanced MCP Server for DocsRay PDF Question-Answering System with Directory Management and Document Summarization"""

import asyncio
import json
import os
import concurrent.futures
import pickle
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from docsray.scripts.file_converter import FileConverter

SCRIPT_DIR = Path(__file__).parent.absolute()
base_dir = SCRIPT_DIR / "data"

# Check models before importing DocsRay modules
def ensure_models_exist():
    """Check if model files exist"""
    try:
        from docsray import MODEL_DIR
    except ImportError:
        MODEL_DIR = Path.home() / ".docsray" / "models"
    
    models = [
        {
            "dir": MODEL_DIR / "bge-m3-gguf",
            "file": "bge-m3-Q8_0.gguf",
        },
        {
            "dir": MODEL_DIR / "multilingual-e5-large-gguf",
            "file": "multilingual-e5-large-Q8_0.gguf",
        },
        {
            "dir": MODEL_DIR / "gemma-3-1b-it-GGUF",
            "file": "gemma-3-1b-it-Q8_0.gguf",
        },
        {
            "dir": MODEL_DIR / "gemma-3-4b-it-GGUF",
            "file": "gemma-3-4b-it-Q8_0.gguf",
        }
    ]
    
    missing_models = []
    for model in models:
        model_path = model["dir"] / model["file"]
        if not model_path.exists():
            missing_models.append(model["file"])
    
    if missing_models:
        print("❌ Required model files are missing:", file=sys.stderr)
        print(f"Expected location: {MODEL_DIR}", file=sys.stderr)
        print("Please download models first with:", file=sys.stderr)
        print("  docsray download-models", file=sys.stderr)
        raise RuntimeError(f"{len(missing_models)} model files are missing: {', '.join(missing_models)}")
    
    print("✅ All required models are ready.", file=sys.stderr)

ensure_models_exist()

# Set environment variable to indicate MCP mode
os.environ['DOCSRAY_MCP_MODE'] = '1'


from docsray.config import FAST_MODE

# MCP imports
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# DocsRay imports
from docsray.chatbot import PDFChatBot, DEFAULT_SYSTEM_PROMPT
from docsray.scripts import pdf_extractor, chunker, build_index, section_rep_builder
from docsray.inference.llm_model import get_llm_models

# Configuration
DATA_DIR = base_dir / "mcp_data"
CACHE_DIR = DATA_DIR / "cache"
CONFIG_FILE = DATA_DIR / "config.json"
DEFAULT_PDF_FOLDER = base_dir / "original"  # Default folder to scan for PDFs
EXTRACT_TIMEOUT = 1800  # 30 minutes

# Create directories
CACHE_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_PDF_FOLDER.mkdir(parents=True, exist_ok=True)

# Global state
current_sections: Optional[List] = None
current_index: Optional[List] = None
current_prompt: str = DEFAULT_SYSTEM_PROMPT
current_pdf_name: Optional[str] = None
current_pdf_folder: Path = DEFAULT_PDF_FOLDER  # Current working directory
current_pages_text: Optional[List[str]] = None  # Store raw page text for summarization

# Enhanced System Prompt for Summarization
SUMMARIZATION_PROMPT = """You are a professional document analyst. Your task is to create a comprehensive summary of a PDF document based on its sections.

Guidelines:
• Provide a structured summary that follows the document's table of contents
• For each section, include key points, main arguments, and important details
• Maintain the hierarchical structure of the document
• Use clear, concise language while preserving technical accuracy
• Include relevant quotes or specific data points when they are crucial
• Highlight connections between different sections when relevant
"""

# Cache Management functions (keeping existing ones)
def _cache_paths(pdf_basename: str) -> Tuple[Path, Path]:
    """Return cache file paths for a PDF."""
    sec_path = CACHE_DIR / f"{pdf_basename}_sections.json"
    idx_path = CACHE_DIR / f"{pdf_basename}_index.pkl"
    return sec_path, idx_path

def _save_cache(pdf_basename: str, sections: List, chunk_index: List) -> None:
    """Save processed PDF data to cache."""
    sec_path, idx_path = _cache_paths(pdf_basename)
    with open(sec_path, "w", encoding="utf-8") as f:
        json.dump(sections, f, ensure_ascii=False, indent=2)
    with open(idx_path, "wb") as f:
        pickle.dump(chunk_index, f)

def _load_cache(pdf_basename: str) -> Tuple[Optional[List], Optional[List]]:
    """Load processed PDF data from cache."""
    sec_path, idx_path = _cache_paths(pdf_basename)
    if sec_path.exists() and idx_path.exists():
        try:
            with open(sec_path, "r", encoding="utf-8") as f:
                sections = json.load(f)
            with open(idx_path, "rb") as f:
                chunk_index = pickle.load(f)
            return sections, chunk_index
        except Exception:
            pass
    return None, None

# Configuration Management
def load_config() -> Dict[str, Any]:
    """Load configuration from file."""
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load config: {e}", file=sys.stderr)
    return {}

def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to file."""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        print(f"Warning: Could not save config: {e}", file=sys.stderr)

def setup_initial_directory() -> Path:
    """Setup initial directory on first run."""
    config = load_config()
    
    # Check if we have a saved directory preference
    if "current_pdf_folder" in config:
        saved_path = Path(config["current_pdf_folder"])
        if saved_path.exists() and saved_path.is_dir():
            print(f"Using saved PDF directory: {saved_path}", file=sys.stderr)
            return saved_path
        else:
            print(f"Saved directory no longer exists: {saved_path}", file=sys.stderr)
    
    # First time setup or saved directory doesn't exist
    print("\n" + "="*60, file=sys.stderr)
    print("🚀 DocsRay MCP Server - Initial Setup", file=sys.stderr)
    print("="*60, file=sys.stderr)
    
    if "current_pdf_folder" not in config:
        print("📁 This appears to be your first time running DocsRay MCP Server.", file=sys.stderr)
    else:
        print("📁 Your saved PDF directory is no longer available.", file=sys.stderr)
    
    # Try some common locations in order of preference
    candidates = [
        Path.home() / "Documents" / "PDFs",
        Path.home() / "Documents",
        Path.home() / "Desktop",
        Path.cwd(),
        DEFAULT_PDF_FOLDER
    ]
    
    print("🔍 Automatically checking common PDF locations...", file=sys.stderr)
    
    selected_path = None
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            # Count PDF files in this directory
            pdf_count = len(list(candidate.glob("*.pdf")))
            if pdf_count > 0:
                print(f"✅ Found {pdf_count} PDF files in: {candidate}", file=sys.stderr)
                selected_path = candidate
                break
            else:
                print(f"📂 Empty directory found: {candidate}", file=sys.stderr)
    
    # If no directory with PDFs found, use Documents or fallback to default
    if selected_path is None:
        documents_dir = Path.home() / "Documents"
        if documents_dir.exists() and documents_dir.is_dir():
            selected_path = documents_dir
            print(f"📂 Using Documents directory: {selected_path}", file=sys.stderr)
        else:
            selected_path = DEFAULT_PDF_FOLDER
            print(f"📂 Using default directory: {selected_path}", file=sys.stderr)
    
    # Save the selection
    config["current_pdf_folder"] = str(selected_path)
    config["setup_completed"] = True
    config["setup_timestamp"] = str(asyncio.get_event_loop().time() if asyncio._get_running_loop() else "unknown")
    save_config(config)
    
    print(f"💾 Saved PDF directory preference: {selected_path}", file=sys.stderr)
    print("💡 You can change this anytime using the 'set_current_directory' tool.", file=sys.stderr)
    print("=" * 60, file=sys.stderr)
    
    return selected_path

# Initialize current directory
current_pdf_folder = setup_initial_directory()

# Directory Management functions
def get_current_directory() -> str:
    """Get current PDF directory path."""
    return str(current_pdf_folder.absolute())

def set_current_directory(folder_path: str) -> Tuple[bool, str]:
    """Set current PDF directory. Returns (success, message)."""
    global current_pdf_folder
    
    try:
        new_path = Path(folder_path).expanduser().resolve()
        
        # Check if directory exists
        if not new_path.exists():
            return False, f"Directory does not exist: {new_path}"
        
        # Check if it's actually a directory
        if not new_path.is_dir():
            return False, f"Path is not a directory: {new_path}"
        
        # Update current directory
        current_pdf_folder = new_path
        
        # Save to config
        config = load_config()
        config["current_pdf_folder"] = str(new_path)
        save_config(config)
        
        return True, f"Current directory changed to: {new_path}"
        
    except Exception as e:
        return False, f"Error setting directory: {str(e)}"

def get_directory_info(folder_path: Optional[str] = None) -> Dict[str, Any]:
    """Get detailed information about the directory including all supported files."""
    if folder_path:
        target_dir = Path(folder_path).expanduser().resolve()
    else:
        target_dir = current_pdf_folder
    
    converter = FileConverter()
    
    info = {
        "path": str(target_dir),
        "exists": target_dir.exists(),
        "is_directory": target_dir.is_dir() if target_dir.exists() else False,
        "pdf_count": 0,
        "other_document_count": 0,
        "supported_files": [],
        "total_size_mb": 0.0,
        "error": None
    }
    
    try:
        if info["exists"] and info["is_directory"]:
            # Get all supported files
            all_files = []
            pdf_count = 0
            other_count = 0
            
            for file_path in sorted(target_dir.iterdir()):
                if file_path.is_file() and converter.is_supported(str(file_path)):
                    try:
                        file_size = file_path.stat().st_size
                        file_type = converter.SUPPORTED_FORMATS.get(
                            file_path.suffix.lower(), 
                            "PDF" if file_path.suffix.lower() == '.pdf' else "Unknown"
                        )
                        
                        all_files.append({
                            "name": file_path.name,
                            "size_mb": file_size / (1024 * 1024),
                            "type": file_type,
                            "is_pdf": file_path.suffix.lower() == '.pdf'
                        })
                        
                        if file_path.suffix.lower() == '.pdf':
                            pdf_count += 1
                        else:
                            other_count += 1
                            
                    except Exception:
                        pass
            
            info["pdf_count"] = pdf_count
            info["other_document_count"] = other_count
            info["supported_files"] = all_files
            info["total_size_mb"] = sum(f["size_mb"] for f in all_files)
            
    except Exception as e:
        info["error"] = str(e)
    
    return info

def list_documents(folder_path: Optional[str] = None) -> List[Dict[str, str]]:
    """Get list of all supported documents in the specified folder."""
    if folder_path:
        doc_dir = Path(folder_path)
    else:
        doc_dir = current_pdf_folder
    
    if not doc_dir.exists():
        return []
    
    converter = FileConverter()
    documents = []
    
    for file_path in doc_dir.iterdir():
        if file_path.is_file() and converter.is_supported(str(file_path)):
            file_type = converter.SUPPORTED_FORMATS.get(
                file_path.suffix.lower(),
                "PDF" if file_path.suffix.lower() == '.pdf' else "Unknown"
            )
            documents.append({
                "name": file_path.name,
                "type": file_type,
                "extension": file_path.suffix.lower()
            })
    
    return sorted(documents, key=lambda x: x["name"])

# Enhanced PDF Processing to store raw text
def process_pdf(pdf_path: str, timeout: int = EXTRACT_TIMEOUT) -> Tuple[List, List, List[str]]:
    """Process PDF and build search index, also return raw pages text."""
    pdf_basename = Path(pdf_path).stem
    
    # Check cache first
    sections, chunk_index = _load_cache(pdf_basename)
    
    # We need to extract anyway to get pages_text for summarization
    print(f"Processing PDF: {pdf_path}", file=sys.stderr)
    
    def _do_extract():
        return pdf_extractor.extract_pdf_content(pdf_path)
    
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_do_extract)
            extracted = future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        raise RuntimeError("PDF extraction timed out.")
    
    pages_text = extracted.get("pages_text", [])
    
    if sections is None or chunk_index is None:
        chunks = chunker.process_extracted_file(extracted)
        chunk_index = build_index.build_chunk_index(chunks)
        sections = section_rep_builder.build_section_reps(extracted["sections"], chunk_index)
        
        _save_cache(pdf_basename, sections, chunk_index)
    
    return sections, chunk_index, pages_text

def get_pdf_list(folder_path: Optional[str] = None) -> List[str]:
    """Get list of PDF files in the specified folder."""
    if folder_path:
        pdf_dir = Path(folder_path)
    else:
        pdf_dir = current_pdf_folder
    
    if not pdf_dir.exists():
        return []
    
    pdf_files = []
    for file_path in pdf_dir.glob("*.pdf"):
        pdf_files.append(file_path.name)
    
    return sorted(pdf_files)


def _section_cache_path(pdf_name: str, section_idx: int, detail_level: str) -> Path:
    """Return cache path for individual section summary."""
    return CACHE_DIR / f"{pdf_name}_section_{section_idx}_{detail_level}.txt"

def summarize_document_by_sections(sections: List, chunk_index: List, 
                                   max_chunks_per_section: int = 5,
                                   brief_mode: bool = False) -> str:
    """
    Create a comprehensive summary of the document organized by sections.
    Process in batches of 10 sections per call.
    """
    local_llm, local_llm_large = get_llm_models()
    
    # Use smaller model for everything in fast mode
    if brief_mode or FAST_MODE:
        summary_model = local_llm
        overall_model = local_llm
    else:
        summary_model = local_llm
        overall_model = local_llm_large
    
    # Determine detail level for cache
    if FAST_MODE:
        detail_level = "brief"
        BATCH_SIZE = 20       
    elif max_chunks_per_section <= 3:
        detail_level = "brief"
        BATCH_SIZE = 20
    elif max_chunks_per_section >= 8:
        detail_level = "detailed"
        BATCH_SIZE = 5
    else:
        detail_level = "standard"
        BATCH_SIZE = 10
    
    summary_parts = []
    summary_parts.append(f"# 📄 Document Summary: {current_pdf_name}\n")
    summary_parts.append("## 📑 Table of Contents\n")
    
    # Create ToC
    for i, section in enumerate(sections):
        title = section.get("title", f"Section {i+1}")
        summary_parts.append(f"{i+1}. {title}")
    
    summary_parts.append("\n## 📊 Section Summaries\n")
    
    # Check which sections need processing
    sections_to_process = []
    cached_summaries = {}
    
    for i, section in enumerate(sections):
        cache_path = _section_cache_path(current_pdf_name, i, detail_level)
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    cached_summaries[i] = f.read()
                print(f"Section {i+1} loaded from cache", file=sys.stderr)
            except Exception:
                sections_to_process.append((i, section))
        else:
            sections_to_process.append((i, section))
    
    # Process only up to N sections per call
    processed_count = 0
    
    if sections_to_process:
        print(f"Need to process {len(sections_to_process)} sections (will process up to {BATCH_SIZE})", file=sys.stderr)
        
        # Process sections sequentially (to avoid segfault)
        for idx, (i, section) in enumerate(sections_to_process[:BATCH_SIZE]):
            processed_count += 1
            title = section.get("title", f"Section {i+1}")
            start_page = section.get("start_page", 0)
            end_page = section.get("end_page", start_page)
            
            print(f"Processing section {i+1}/{len(sections)}: {title}", file=sys.stderr)
            
            # Get chunks for this section
            section_chunks = [
                chunk for chunk in chunk_index 
                if chunk["metadata"].get("section_title") == title
            ]
            
            if not section_chunks:
                summary_text = "*No content found for this section.*"
            else:
                # In fast mode, use fewer chunks
                if brief_mode:
                    max_chunks = min(3, max_chunks_per_section)
                else:
                    max_chunks = max_chunks_per_section
                
                # Select most representative chunks
                if len(section_chunks) <= max_chunks:
                    selected_chunks = section_chunks
                else:
                    # Take first, middle, and last chunks
                    first_idx = max_chunks // 3
                    last_idx = max_chunks // 3
                    middle_idx = max_chunks - first_idx - last_idx
                    
                    selected_chunks = (
                        section_chunks[:first_idx] + 
                        section_chunks[len(section_chunks)//2 - middle_idx//2 : len(section_chunks)//2 + middle_idx//2 + 1] +
                        section_chunks[-last_idx:]
                    )
                
                # Combine chunk contents (limit length in fast mode)
                combined_content = "\n".join([
                    chunk["metadata"].get("content", "")[:500 if brief_mode else 1000]
                    for chunk in selected_chunks
                ])
                
                # Simplified prompt for fast mode
                if brief_mode:
                    section_prompt = f"""Summarize this section "{title}" in 2-3 sentences:
{combined_content[:1500]}

Summary:"""
                else:
                    section_prompt = f"""Based on the following content from section "{title}", provide a concise summary 
highlighting the main points, key arguments, and important details:

{combined_content}

Summary (2-3 paragraphs):"""
                
                try:
                    start_time = time.time()
                    summary_response = summary_model.generate(section_prompt)
                    
                    # Extract the actual summary from response
                    summary_text = summary_model.strip_response(summary_response)
  
                    elapsed = time.time() - start_time
                    print(f"Section {i+1} summarized in {elapsed:.1f}s", file=sys.stderr)
                    
                except Exception as e:
                    summary_text = f"*Error generating summary: {str(e)}*"
            
            # Save to cache
            cache_path = _section_cache_path(current_pdf_name, i, detail_level)
            try:
                with open(cache_path, 'w', encoding='utf-8') as f:
                    f.write(f"### {i+1}. {title}\n*Pages {start_page}-{end_page}*\n\n{summary_text}")
                print(f"Section {i+1} saved to cache", file=sys.stderr)
            except Exception as e:
                print(f"Failed to cache section {i+1}: {e}", file=sys.stderr)
            
            cached_summaries[i] = f"### {i+1}. {title}\n*Pages {start_page}-{end_page}*\n\n{summary_text}"
    
    # Add all section summaries in order
    for i in range(len(sections)):
        if i in cached_summaries:
            summary_parts.append(cached_summaries[i])
            summary_parts.append("")  # Empty line between sections
    
    # Show progress information
    total_cached = len(cached_summaries)
    total_sections = len(sections)
    
    if total_cached < total_sections:
        remaining = total_sections - total_cached
        summary_parts.append(f"\n---\n⏳ **Progress: {total_cached}/{total_sections} sections completed**")
        summary_parts.append(f"📝 {remaining} sections remaining. Run 'summarize_document' again to continue.\n---\n")
    else:
        # Add overall document summary only when all sections are complete
        if not brief_mode and len(sections) <= 10:
            summary_parts.append("## 🎯 Overall Document Summary\n")
            
            # Check if overall summary is cached
            overall_cache_path = CACHE_DIR / f"{current_pdf_name}_overall_{detail_level}.txt"
            if overall_cache_path.exists():
                try:
                    with open(overall_cache_path, 'r', encoding='utf-8') as f:
                        overall_summary = f.read()
                    summary_parts.append(overall_summary)
                except Exception:
                    pass
            else:
                # Create a high-level summary using section titles and brief content
                section_titles = ', '.join([s.get('title', '') for s in sections[:10]])
                
                overall_prompt = f"""Based on a document with these sections: {section_titles}

Provide a brief executive summary (2-3 paragraphs) highlighting the main theme and key findings."""
                
                try:
                    print("Generating overall summary...", file=sys.stderr)
                    start_time = time.time()
                    overall_response = overall_model.generate(overall_prompt)
                    
                    if hasattr(overall_model, 'strip_response'):
                        overall_summary = overall_model.strip_response(overall_response)
                    else:
                        if "<|im_start|>assistant" in overall_response:
                            overall_summary = overall_response.split("<|im_start|>assistant")[1].split("<|im_end|>")[0].strip()
                        else:
                            overall_summary = overall_response.strip()
                    
                    # Cache overall summary
                    try:
                        with open(overall_cache_path, 'w', encoding='utf-8') as f:
                            f.write(overall_summary)
                    except Exception:
                        pass
                        
                    elapsed = time.time() - start_time
                    print(f"Overall summary generated in {elapsed:.1f}s", file=sys.stderr)
                    
                    summary_parts.append(overall_summary)
                except Exception as e:
                    summary_parts.append(f"*Error generating overall summary: {str(e)}*")
    
    return "\n".join(summary_parts)

def clear_all_cache() -> Tuple[bool, str]:
    """Clear all cache files in the cache directory."""
    try:
        cache_files = list(CACHE_DIR.glob("*"))
        if not cache_files:
            return True, "No cache files to clear."
        
        cleared_count = 0
        failed_count = 0
        total_size = 0
        
        for cache_file in cache_files:
            if cache_file.is_file():
                try:
                    file_size = cache_file.stat().st_size
                    cache_file.unlink()
                    cleared_count += 1
                    total_size += file_size
                except Exception as e:
                    print(f"Failed to delete {cache_file.name}: {e}", file=sys.stderr)
                    failed_count += 1
        
        # Format size
        if total_size > 1024 * 1024:
            size_str = f"{total_size / (1024 * 1024):.1f} MB"
        else:
            size_str = f"{total_size / 1024:.1f} KB"
        
        if failed_count == 0:
            return True, f"Successfully cleared {cleared_count} cache files ({size_str})"
        else:
            return True, f"Cleared {cleared_count} files ({size_str}), failed to clear {failed_count} files"
            
    except Exception as e:
        return False, f"Error clearing cache: {str(e)}"

def get_cache_info() -> Dict[str, Any]:
    """Get information about the cache directory."""
    try:
        cache_files = list(CACHE_DIR.glob("*"))
        
        # Categorize cache files
        pdf_sections = {}  # PDF name -> section count
        pdf_indices = {}   # PDF name -> has index
        pdf_summaries = {} # PDF name -> summary levels
        other_files = []
        
        total_size = 0
        
        for cache_file in cache_files:
            if cache_file.is_file():
                file_size = cache_file.stat().st_size
                total_size += file_size
                
                name = cache_file.name
                
                # Section cache files
                if "_sections.json" in name:
                    pdf_name = name.replace("_sections.json", "")
                    pdf_sections[pdf_name] = pdf_sections.get(pdf_name, 0) + 1
                
                # Index cache files
                elif "_index.pkl" in name:
                    pdf_name = name.replace("_index.pkl", "")
                    pdf_indices[pdf_name] = True
                
                # Section summary cache files
                elif "_section_" in name and name.endswith(".txt"):
                    parts = name.split("_section_")
                    if len(parts) == 2:
                        pdf_name = parts[0]
                        # Extract detail level from filename
                        if "_brief.txt" in parts[1]:
                            level = "brief"
                        elif "_detailed.txt" in parts[1]:
                            level = "detailed"
                        else:
                            level = "standard"
                        
                        if pdf_name not in pdf_summaries:
                            pdf_summaries[pdf_name] = {"brief": 0, "standard": 0, "detailed": 0}
                        pdf_summaries[pdf_name][level] += 1
                
                # Overall summary cache files
                elif "_overall_" in name and name.endswith(".txt"):
                    parts = name.split("_overall_")
                    if len(parts) == 2:
                        pdf_name = parts[0]
                        level = parts[1].replace(".txt", "")
                        if pdf_name not in pdf_summaries:
                            pdf_summaries[pdf_name] = {"brief": 0, "standard": 0, "detailed": 0}
                        pdf_summaries[pdf_name][f"{level}_overall"] = True
                
                else:
                    other_files.append(name)
        
        return {
            "total_files": len(cache_files),
            "total_size_mb": total_size / (1024 * 1024),
            "pdf_sections": pdf_sections,
            "pdf_indices": pdf_indices,
            "pdf_summaries": pdf_summaries,
            "other_files": other_files,
            "cache_dir": str(CACHE_DIR)
        }
        
    except Exception as e:
        return {
            "error": str(e),
            "cache_dir": str(CACHE_DIR)
        }
    
# MCP Server Setup
server = Server("docsray-mcp")

@server.list_tools()
async def list_tools() -> List[Tool]:
    """List available tools."""
    return [
        Tool(
            name="get_current_directory",
            description="Get the current PDF directory path",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="set_current_directory",
            description="Set the current PDF directory",
            inputSchema={
                "type": "object",
                "properties": {
                    "folder_path": {"type": "string", "description": "New directory path to set as current"}
                },
                "required": ["folder_path"]
            }
        ),
        Tool(
            name="get_directory_info",
            description="Get detailed information about a directory (current or specified)",
            inputSchema={
                "type": "object",
                "properties": {
                    "folder_path": {"type": "string", "description": "Directory path to inspect (optional, uses current if not specified)"}
                }
            }
        ),
        Tool(
            name="list_documents",
            description="List all supported documents (PDFs, Word, Excel, PowerPoint, images, etc.) in the current or specified folder",
            inputSchema={
                "type": "object",
                "properties": {
                    "folder_path": {"type": "string", "description": "Folder path to scan (optional, uses current if not specified)"}
                }
            }
        ),
        Tool(
            name="load_document",
            description="Load and process any supported document file with optional visual analysis",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Document filename to load"},
                    "folder_path": {"type": "string", "description": "Folder path (optional, uses current if not specified)"},
                    "analyze_visuals": {
                        "type": "boolean", 
                        "description": "Whether to analyze visual content (default: true, disabled in FAST_MODE)",
                        "default": True
                    }
                },
                "required": ["filename"]
            }
        ),
        Tool(
            name="reset_initial_setup",
            description="Reset initial setup and configure PDF directory again",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="ask_question",
            description="Ask a question about the loaded PDF",
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "Question to ask"},
                    "use_coarse_search": {"type": "boolean", "description": "Use coarse-to-fine search (default: true)"}
                },
                "required": ["question"]
            }
        ),
        Tool(
            name="summarize_document",
            description="Generate a comprehensive summary of the loaded PDF organized by sections",
            inputSchema={
                "type": "object",
                "properties": {
                    "detail_level": {
                        "type": "string", 
                        "description": "Level of detail for summary: 'brief', 'standard', or 'detailed'",
                        "enum": ["brief", "standard", "detailed"],
                        "default": "standard"
                    }
                }
            }
        ),
        Tool(
            name="clear_all_cache",
            description="Clear all cache files (sections, indices, and summaries)",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_cache_info",
            description="Get information about cached files",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        )

    ]

@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Execute a tool and return results."""
    global current_sections, current_index, current_pdf_name, current_pages_text
    
    try:
        if name == "get_current_directory":
            current_dir = get_current_directory()
            dir_info = get_directory_info()
            
            response = f"📁 **Current PDF Directory:**\n"
            response += f"🗂️ Path: `{current_dir}`\n"
            response += f"📊 PDF files: {dir_info['pdf_count']}\n"
            
            if dir_info['pdf_count'] > 0:
                response += f"💾 Total size: {dir_info['total_size_mb']:.1f} MB\n"
            
            if not dir_info['exists']:
                response += "\n⚠️ Directory does not exist!"
            elif not dir_info['is_directory']:
                response += "\n⚠️ Path is not a directory!"
            
            return [TextContent(type="text", text=response)]
        
        elif name == "set_current_directory":
            folder_path = arguments["folder_path"]
            success, message = set_current_directory(folder_path)
            
            if success:
                dir_info = get_directory_info()
                response = f"✅ {message}\n"
                response += f"📊 Found {dir_info['pdf_count']} PDF files"
                if dir_info['pdf_count'] > 0:
                    response += f" ({dir_info['total_size_mb']:.1f} MB total)"
            else:
                response = f"❌ {message}"
            
            return [TextContent(type="text", text=response)]
        
        elif name == "get_directory_info":
            folder_path = arguments.get("folder_path")
            dir_info = get_directory_info(folder_path)
            
            target_path = folder_path if folder_path else "current directory"
            
            if dir_info['error']:
                response = f"❌ Error accessing {target_path}: {dir_info['error']}"
            elif not dir_info['exists']:
                response = f"❌ Directory does not exist: {dir_info['path']}"
            elif not dir_info['is_directory']:
                response = f"❌ Path is not a directory: {dir_info['path']}"
            else:
                response = f"📁 **Directory Information:**\n"
                response += f"🗂️ Path: `{dir_info['path']}`\n"
                response += f"📊 PDF files: {dir_info['pdf_count']}\n"
                
                if dir_info['pdf_count'] > 0:
                    response += f"💾 Total size: {dir_info['total_size_mb']:.1f} MB\n\n"
                    response += "📄 **PDF Files:**\n"
                    
                    for i, file_info in enumerate(dir_info['pdf_files'], 1):
                        response += f"{i}. {file_info['name']} ({file_info['size_mb']:.1f} MB)\n"
                else:
                    response += "\n📭 No PDF files found in this directory."
            
            return [TextContent(type="text", text=response)]
        
        elif name == "list_documents":
            folder_path = arguments.get("folder_path")
            doc_list = list_documents(folder_path)
            
            if folder_path:
                folder_name = folder_path
            else:
                folder_name = f"current directory ({current_pdf_folder})"
            
            if not doc_list:
                return [TextContent(type="text", text=f"❌ No supported documents found in {folder_name}")]
            
            # Group by type
            by_type = {}
            for doc in doc_list:
                doc_type = doc["type"]
                if doc_type not in by_type:
                    by_type[doc_type] = []
                by_type[doc_type].append(doc["name"])
            
            # Format the list
            response = f"📁 Found {len(doc_list)} supported documents in {folder_name}:\n\n"
            
            for doc_type, files in sorted(by_type.items()):
                response += f"**{doc_type}** ({len(files)} files):\n"
                for i, filename in enumerate(files, 1):
                    response += f"  {i}. {filename}\n"
                response += "\n"
            
            response += f"💡 Use 'load_document' with the filename to process any of these files."
            
            return [TextContent(type="text", text=response)]
       
        elif name == "load_document":
            filename = arguments["filename"]
            folder_path = arguments.get("folder_path")
            analyze_visuals = arguments.get("analyze_visuals", True)
            
            if folder_path:
                file_path = Path(folder_path) / filename
            else:
                file_path = current_pdf_folder / filename
            
            # Check if file exists
            if not file_path.exists():
                # Try with common extensions if no extension provided
                if '.' not in filename:
                    converter = FileConverter()
                    for ext in converter.SUPPORTED_FORMATS.keys():
                        test_path = file_path.parent / f"{filename}{ext}"
                        if test_path.exists():
                            file_path = test_path
                            break
                
                if not file_path.exists():
                    return [TextContent(type="text", text=f"❌ Document file not found: {file_path}")]
            
            # Process the document (auto-conversion handled by extract_content)
            # Process the document with visual analysis option
            try:
                from docsray.scripts import pdf_extractor
                
                # extract_content 호출 시 analyze_visuals 전달
                extracted = pdf_extractor.extract_content(
                    str(file_path),
                    analyze_visuals=analyze_visuals
                )
                # Process extracted content
                chunks = chunker.process_extracted_file(extracted)
                chunk_index = build_index.build_chunk_index(chunks)
                sections = section_rep_builder.build_section_reps(extracted["sections"], chunk_index)
                
                current_sections = sections
                current_index = chunk_index
                current_pdf_name = file_path.name
                current_pages_text = extracted.get("pages_text", [])
                
                # Get file info
                file_size = file_path.stat().st_size / (1024 * 1024)  # MB
                num_sections = len(sections)
                num_chunks = len(chunk_index)
                num_pages = len(current_pages_text)
                
                response = f"✅ Successfully loaded: {file_path.name}\n"
                response += f"📂 From: {file_path.parent}\n"
                
                if extracted["metadata"].get("was_converted", False):
                    original_format = extracted["metadata"].get("original_format", "unknown")
                    response += f"🔄 Converted from: {original_format.upper()} to PDF\n"
                
                if FAST_MODE:
                    response += f"⚡ Visual analysis: Disabled (FAST_MODE)\n"
                else:
                    response += f"👁️ Visual analysis: {'Enabled' if analyze_visuals else 'Disabled'}\n"
                
                response += f"📊 File size: {file_size:.1f} MB\n"
                response += f"📄 Pages: {num_pages}\n"
                response += f"📑 Sections: {num_sections}\n"
                response += f"🔍 Chunks: {num_chunks}\n\n"
                response += "You can now:\n"
                response += "• Ask questions about this document using 'ask_question'\n"
                response += "• Generate a comprehensive summary using 'summarize_document'"
                
                return [TextContent(type="text", text=response)]

            except Exception as e:
                return [TextContent(type="text", text=f"❌ Error processing document: {str(e)}")]
             
        elif name == "reset_initial_setup":
            # Reset config and run initial setup again
            try:
                # Remove the saved directory preference
                config = load_config()
                if "current_pdf_folder" in config:
                    del config["current_pdf_folder"]
                if "setup_completed" in config:
                    del config["setup_completed"]
                save_config(config)
                
                # Run setup again
                globals()['current_pdf_folder'] = setup_initial_directory()
                dir_info = get_directory_info()
                response = f"🔄 **Initial setup reset completed!**\n"
                response += f"📁 New current directory: `{current_pdf_folder}`\n"
                response += f"📊 Found {dir_info['pdf_count']} PDF files"
                if dir_info['pdf_count'] > 0:
                    response += f" ({dir_info['total_size_mb']:.1f} MB total)"
                
                return [TextContent(type="text", text=response)]
                
            except Exception as e:
                return [TextContent(type="text", text=f"❌ Error resetting setup: {str(e)}")]
        
        elif name == "ask_question":
            if current_sections is None or current_index is None:
                return [TextContent(type="text", text="❌ Please load a PDF first using 'load_document'")]
            
            question = arguments["question"]
            use_coarse = arguments.get("use_coarse_search", True)
            fine_only = not use_coarse
            
            # Create chatbot and get answer
            chatbot = PDFChatBot(current_sections, current_index, system_prompt=current_prompt)
            answer_output, reference_output = chatbot.answer(question, max_iterations=1, fine_only=fine_only)
            
            # Format response
            response = f"📄 **Current PDF:** {current_pdf_name}\n"
            response += f"❓ **Question:** {question}\n\n"
            response += f"💡 **Answer:**\n{answer_output}\n\n"
            response += f"📚 **References:**\n{reference_output}"
            
            return [TextContent(type="text", text=response)]
        
        elif name == "summarize_document":
            if current_sections is None or current_index is None:
                return [TextContent(type="text", text="❌ Please load a PDF first using 'load_document'")]
            
            detail_level = arguments.get("detail_level", "standard")
            
            # Adjust parameters based on detail level
            if FAST_MODE:
                detail_level = "brief"  # Force brief mode in fast mode
                
            if detail_level == "brief":
                max_chunks = 3
                brief_mode = True

            elif detail_level == "detailed":
                max_chunks = 8
                brief_mode = False

            else:  # standard
                max_chunks = 5
                brief_mode = False

            # Check for cached summary first
            cache_key = f"{current_pdf_name}_summary_{detail_level}.txt"
            cache_path = CACHE_DIR / cache_key
            
            if cache_path.exists():
                try:
                    with open(cache_path, 'r', encoding='utf-8') as f:
                        cached_summary = f.read()
                    response = f"📄 **Cached {detail_level} summary for:** {current_pdf_name}\n\n"
                    response += cached_summary
                    return [TextContent(type="text", text=response)]
                except Exception:
                    pass  # If cache read fails, regenerate
            
            # Generate summary
            response = f"📄 **Generating {detail_level} summary for:** {current_pdf_name}\n"
            
            # Show estimated time based on sections
            num_sections = len(current_sections)
            if detail_level == "brief":
                estimated_time = num_sections * 2  # ~2 seconds per section in fast mode
            else:
                estimated_time = num_sections * 5  # ~5 seconds per section in normal mode
            
            response += f"⏳ Estimated time: ~{estimated_time} seconds for {num_sections} sections...\n\n"
            
            try:
                start_time = time.time()
                
                summary = summarize_document_by_sections(
                    current_sections, 
                    current_index,
                    max_chunks_per_section=max_chunks,
                    brief_mode=brief_mode
                )
                
                elapsed = time.time() - start_time
                
                # Save to cache
                try:
                    with open(cache_path, 'w', encoding='utf-8') as f:
                        f.write(summary)
                except Exception:
                    pass  # Ignore cache write errors
                
                response += summary
                response += f"\n\n⏱️ Summary generated in {elapsed:.1f} seconds"
                
            except Exception as e:
                response += f"❌ Error generating summary: {str(e)}"
            
            return [TextContent(type="text", text=response)]
        elif name == "clear_all_cache":
            # Get cache info before clearing
            cache_info = get_cache_info()
            
            # Clear cache
            success, message = clear_all_cache()
            
            response = f"🗑️ **Cache Clearing Result:**\n"
            
            if cache_info.get("error"):
                response += f"⚠️ Could not get cache info: {cache_info['error']}\n"
            else:
                response += f"📊 Before clearing:\n"
                response += f"   • Files: {cache_info['total_files']}\n"
                response += f"   • Size: {cache_info['total_size_mb']:.1f} MB\n"
                
                if cache_info['pdf_sections'] or cache_info['pdf_summaries']:
                    response += f"   • PDFs with cache: {len(set(list(cache_info['pdf_sections'].keys()) + list(cache_info['pdf_summaries'].keys())))}\n"
            
            response += f"\n{'✅' if success else '❌'} {message}\n"
            
            if success:
                response += "\n💡 All cache has been cleared. PDFs will need to be reprocessed."
            
            return [TextContent(type="text", text=response)]
        
        elif name == "get_cache_info":
            cache_info = get_cache_info()
            
            if cache_info.get("error"):
                return [TextContent(type="text", text=f"❌ Error getting cache info: {cache_info['error']}")]
            
            response = f"📊 **Cache Information:**\n"
            response += f"📁 Cache directory: `{cache_info['cache_dir']}`\n"
            response += f"📄 Total files: {cache_info['total_files']}\n"
            response += f"💾 Total size: {cache_info['total_size_mb']:.1f} MB\n\n"
            
            # PDFs with cached data
            all_pdfs = set()
            if cache_info['pdf_sections']:
                all_pdfs.update(cache_info['pdf_sections'].keys())
            if cache_info['pdf_indices']:
                all_pdfs.update(cache_info['pdf_indices'].keys())
            if cache_info['pdf_summaries']:
                all_pdfs.update(cache_info['pdf_summaries'].keys())
            
            if all_pdfs:
                response += f"📚 **Cached PDFs ({len(all_pdfs)}):**\n"
                for pdf_name in sorted(all_pdfs):
                    response += f"\n**{pdf_name}:**\n"
                    
                    # Check what's cached for this PDF
                    has_sections = pdf_name in cache_info['pdf_sections']
                    has_index = pdf_name in cache_info['pdf_indices']
                    summaries = cache_info['pdf_summaries'].get(pdf_name, {})
                    
                    if has_sections or has_index:
                        response += f"  • {'✅' if has_sections else '❌'} Sections data\n"
                        response += f"  • {'✅' if has_index else '❌'} Search index\n"
                    
                    if summaries:
                        for level in ["brief", "standard", "detailed"]:
                            count = summaries.get(level, 0)
                            has_overall = summaries.get(f"{level}_overall", False)
                            if count > 0 or has_overall:
                                response += f"  • {level.capitalize()} summary: {count} sections"
                                if has_overall:
                                    response += " + overall"
                                response += "\n"
            else:
                response += "📭 No cached PDFs found.\n"
            
            if cache_info['other_files']:
                response += f"\n📎 Other files: {len(cache_info['other_files'])}\n"
            
            response += f"\n💡 Use 'clear_all_cache' to remove all cached data."
            
            return [TextContent(type="text", text=response)]
        
        else:
            return [TextContent(type="text", text=f"❌ Unknown tool: {name}")]
            
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return [TextContent(type="text", text=f"❌ Error: {str(e)}\n\nDetails:\n{error_details}")]

async def run_mcp_server():
    """Run the MCP server (async version)."""
    print(f"Starting DocsRay MCP Server (Enhanced with Directory Management and Summarization)...", file=sys.stderr)
    print(f"Default PDF Folder: {DEFAULT_PDF_FOLDER}", file=sys.stderr)
    print(f"Current PDF Folder: {current_pdf_folder}", file=sys.stderr)
    print(f"Cache Directory: {CACHE_DIR}", file=sys.stderr)
    print(f"Config File: {CONFIG_FILE}", file=sys.stderr)
    print(f"Fast Mode: {'Enabled' if FAST_MODE else 'Disabled'}", file=sys.stderr)
    
    # Show available PDFs on startup
    pdf_list = get_pdf_list()
    if pdf_list:
        print(f"Available PDFs: {', '.join(pdf_list[:5])}", file=sys.stderr)
        if len(pdf_list) > 5:
            print(f"... and {len(pdf_list) - 5} more PDFs", file=sys.stderr)
    else:
        print("No PDFs found in current folder.", file=sys.stderr)
        print("💡 Use 'set_current_directory' to change to a folder with PDF files.", file=sys.stderr)
    
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )

def main():
    """Entry point for docsray mcp command (sync version for PyPI)."""
    try:
        asyncio.run(run_mcp_server())
    except KeyboardInterrupt:
        print("\n🛑 MCP Server stopped by user", file=sys.stderr)
    except Exception as e:
        print(f"❌ MCP Server error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()