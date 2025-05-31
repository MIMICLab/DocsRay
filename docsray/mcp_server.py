#!/usr/bin/env python3
# mcp_server.py - Enhanced version with document summarization

"""Enhanced MCP Server for DocsRay PDF Question-Answering System with Directory Management and Document Summarization"""

import asyncio
import json
import os
import concurrent.futures
import pickle
import sys
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

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
            "dir": MODEL_DIR / "trillion-7b-preview-GGUF",
            "file": "trillion-7b-preview.q8_0.gguf",
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
    """Get detailed information about the directory."""
    if folder_path:
        target_dir = Path(folder_path).expanduser().resolve()
    else:
        target_dir = current_pdf_folder
    
    info = {
        "path": str(target_dir),
        "exists": target_dir.exists(),
        "is_directory": target_dir.is_dir() if target_dir.exists() else False,
        "pdf_count": 0,
        "pdf_files": [],
        "total_size_mb": 0.0,
        "error": None
    }
    
    try:
        if info["exists"] and info["is_directory"]:
            pdf_files = list(target_dir.glob("*.pdf"))
            info["pdf_count"] = len(pdf_files)
            
            total_size = 0
            pdf_list = []
            
            for pdf_file in sorted(pdf_files):
                try:
                    file_size = pdf_file.stat().st_size
                    total_size += file_size
                    pdf_list.append({
                        "name": pdf_file.name,
                        "size_mb": file_size / (1024 * 1024)
                    })
                except Exception:
                    pdf_list.append({
                        "name": pdf_file.name,
                        "size_mb": 0.0
                    })
            
            info["pdf_files"] = pdf_list
            info["total_size_mb"] = total_size / (1024 * 1024)
            
    except Exception as e:
        info["error"] = str(e)
    
    return info

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

# Document Summarization Function
def summarize_document_by_sections(sections: List, chunk_index: List, max_chunks_per_section: int = 5) -> str:
    """
    Create a comprehensive summary of the document organized by sections.
    
    Args:
        sections: List of section dictionaries
        chunk_index: List of chunk dictionaries with embeddings and metadata
        max_chunks_per_section: Maximum number of chunks to use per section for summary
    
    Returns:
        Formatted summary string
    """
    local_llm, local_llm_large = get_llm_models()
    
    summary_parts = []
    summary_parts.append(f"# 📄 Document Summary: {current_pdf_name}\n")
    summary_parts.append("## 📑 Table of Contents\n")
    
    # Create ToC
    for i, section in enumerate(sections):
        title = section.get("title", f"Section {i+1}")
        summary_parts.append(f"{i+1}. {title}")
    
    summary_parts.append("\n## 📊 Section Summaries\n")
    
    # Summarize each section
    for i, section in enumerate(sections):
        title = section.get("title", f"Section {i+1}")
        start_page = section.get("start_page", 0)
        end_page = section.get("end_page", start_page)
        
        summary_parts.append(f"### {i+1}. {title}")
        summary_parts.append(f"*Pages {start_page}-{end_page}*\n")
        
        # Get chunks for this section
        section_chunks = [
            chunk for chunk in chunk_index 
            if chunk["metadata"].get("section_title") == title
        ]
        
        if not section_chunks:
            summary_parts.append("*No content found for this section.*\n")
            continue
        
        # Select most representative chunks (first and last few)
        if len(section_chunks) <= max_chunks_per_section:
            selected_chunks = section_chunks
        else:
            # Take first 2, last 2, and middle chunks
            first_chunks = section_chunks[:2]
            last_chunks = section_chunks[-2:]
            middle_idx = len(section_chunks) // 2
            middle_chunks = section_chunks[middle_idx-1:middle_idx+1]
            selected_chunks = first_chunks + middle_chunks + last_chunks
        
        # Combine chunk contents
        combined_content = "\n".join([
            chunk["metadata"].get("content", "") 
            for chunk in selected_chunks
        ])
        
        # Generate section summary using LLM
        section_prompt = f"""Based on the following content from section "{title}", provide a concise summary 
highlighting the main points, key arguments, and important details:

{combined_content}

Summary (2-3 paragraphs):"""
        
        try:
            summary_response = local_llm.generate(section_prompt)
            # Extract the actual summary from response
            if "<start_of_turn>model" in summary_response:
                section_summary = summary_response.split("<start_of_turn>model")[1].split("<end_of_turn>")[0].strip()
            else:
                section_summary = summary_response.strip()
            
            summary_parts.append(section_summary)
        except Exception as e:
            summary_parts.append(f"*Error generating summary: {str(e)}*")
        
        summary_parts.append("")  # Empty line between sections
    
    # Add overall document summary
    summary_parts.append("## 🎯 Overall Document Summary\n")
    
    # Create a high-level summary
    overall_prompt = f"""Based on the document with the following sections:
{', '.join([s.get('title', '') for s in sections])}

Provide a high-level executive summary of the entire document in 2-3 paragraphs, 
highlighting the main theme, key findings, and overall significance."""
    
    try:
        overall_response = local_llm_large.generate(overall_prompt)
        if "<|im_start|>assistant" in overall_response:
            overall_summary = overall_response.split("<|im_start|>assistant")[1].split("<|im_end|>")[0].strip()
        else:
            overall_summary = overall_response.strip()
        summary_parts.append(overall_summary)
    except Exception as e:
        summary_parts.append(f"*Error generating overall summary: {str(e)}*")
    
    return "\n".join(summary_parts)

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
            name="list_pdfs",
            description="List all PDF files in the current or specified folder",
            inputSchema={
                "type": "object",
                "properties": {
                    "folder_path": {"type": "string", "description": "Folder path to scan (optional, uses current if not specified)"}
                }
            }
        ),
        Tool(
            name="load_pdf",
            description="Load and process a PDF file from the current or specified folder",
            inputSchema={
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "PDF filename to load"},
                    "folder_path": {"type": "string", "description": "Folder path (optional, uses current if not specified)"}
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
        
        elif name == "list_pdfs":
            folder_path = arguments.get("folder_path")
            pdf_list = get_pdf_list(folder_path)
            
            if folder_path:
                folder_name = folder_path
            else:
                folder_name = f"current directory ({current_pdf_folder})"
            
            if not pdf_list:
                return [TextContent(type="text", text=f"❌ No PDF files found in {folder_name}")]
            
            # Format the list
            response = f"📁 Found {len(pdf_list)} PDF files in {folder_name}:\n\n"
            for i, pdf_name in enumerate(pdf_list, 1):
                response += f"{i}. {pdf_name}\n"
            
            response += f"\n💡 Use 'load_pdf' with the filename to process any of these PDFs."
            
            return [TextContent(type="text", text=response)]
        
        elif name == "load_pdf":
            filename = arguments["filename"]
            folder_path = arguments.get("folder_path")
            
            # Ensure filename ends with .pdf
            if not filename.endswith('.pdf'):
                filename += '.pdf'
            
            # Determine full path
            if folder_path:
                pdf_path = Path(folder_path) / filename
            else:
                pdf_path = current_pdf_folder / filename
            
            # Check if file exists
            if not pdf_path.exists():
                return [TextContent(type="text", text=f"❌ PDF file not found: {pdf_path}")]
            
            # Process the PDF
            try:
                sections, chunk_index, pages_text = process_pdf(str(pdf_path))
                current_sections = sections
                current_index = chunk_index
                current_pdf_name = filename
                current_pages_text = pages_text
                
                # Get file info
                file_size = pdf_path.stat().st_size / (1024 * 1024)  # MB
                num_sections = len(sections)
                num_chunks = len(chunk_index)
                num_pages = len(pages_text)
                
                response = f"✅ Successfully loaded: {filename}\n"
                response += f"📂 From: {pdf_path.parent}\n"
                response += f"📊 File size: {file_size:.1f} MB\n"
                response += f"📄 Pages: {num_pages}\n"
                response += f"📑 Sections: {num_sections}\n"
                response += f"🔍 Chunks: {num_chunks}\n\n"
                response += "You can now:\n"
                response += "• Ask questions about this PDF using 'ask_question'\n"
                response += "• Generate a comprehensive summary using 'summarize_document'"
                
                return [TextContent(type="text", text=response)]
            except Exception as e:
                return [TextContent(type="text", text=f"❌ Error processing PDF: {str(e)}")]
        
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
                return [TextContent(type="text", text="❌ Please load a PDF first using 'load_pdf'")]
            
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
                return [TextContent(type="text", text="❌ Please load a PDF first using 'load_pdf'")]
            
            detail_level = arguments.get("detail_level", "standard")
            
            # Adjust parameters based on detail level
            if detail_level == "brief":
                max_chunks = 3
            elif detail_level == "detailed":
                max_chunks = 8
            else:  # standard
                max_chunks = 5
            
            # Generate summary
            response = f"📄 **Generating {detail_level} summary for:** {current_pdf_name}\n"
            response += "⏳ This may take a moment...\n\n"
            
            try:
                summary = summarize_document_by_sections(
                    current_sections, 
                    current_index,
                    max_chunks_per_section=max_chunks
                )
                response += summary
            except Exception as e:
                response += f"❌ Error generating summary: {str(e)}"
            
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