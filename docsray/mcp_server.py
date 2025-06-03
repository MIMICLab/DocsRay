#!/usr/bin/env python3
# mcp_server.py - Enhanced version with visual analysis toggle

"""Enhanced MCP Server for DocsRay PDF Question-Answering System with Visual Analysis Control"""

import asyncio
import json
import os
import pickle
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import numpy as np

# MCP imports
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# DocsRay imports
from docsray.chatbot import PDFChatBot, DEFAULT_SYSTEM_PROMPT
from docsray.scripts import pdf_extractor, chunker, build_index, section_rep_builder
from docsray.inference.llm_model import local_llm, local_llm_large
from docsray.inference.embedding_model import embedding_model
from docsray.scripts.file_converter import FileConverter
from docsray.config import FAST_MODE, DISABLE_VISUAL_ANALYSIS
from docsray.config import MODEL_DIR, FAST_MODE, STANDARD_MODE, FULL_FEATURE_MODE
from docsray.download_models import check_models
from docsray.search.vector_search import vector_search_with_metadata

SCRIPT_DIR = Path(__file__).parent.absolute()
base_dir = SCRIPT_DIR / "data"

import platform
from datetime import datetime


# Set environment variable to indicate MCP mode
os.environ['DOCSRAY_MCP_MODE'] = '1'

# Configuration
DATA_DIR = base_dir / "mcp_data"
CACHE_DIR = DATA_DIR / "cache"
CONFIG_FILE = DATA_DIR / "config.json"
DEFAULT_PDF_FOLDER = base_dir / "original"  # Default folder to scan for PDFs
   
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
search_in_progress = False
search_stop_flag = False
search_results_cache = {}


# Visual analysis global setting
visual_analysis_enabled: bool = not DISABLE_VISUAL_ANALYSIS 

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

check_models()

def get_recommended_search_paths() -> List[Dict[str, Any]]:
    """
    Get recommended search paths based on the operating system and common document locations.
    Returns a list of recommended paths with descriptions and document counts.
    """
    recommendations = []
    home = Path.home()
    system = platform.system()
    
    # Common paths for all systems
    common_paths = [
        {"path": home, "description": "Your home directory", "category": "general"},
    ]
    
    # OS-specific paths
    if system == "Windows":
        common_paths.extend([
            {"path": home / "Documents", "description": "Documents folder", "category": "primary"},
            {"path": home / "Desktop", "description": "Desktop folder", "category": "primary"},
            {"path": home / "Downloads", "description": "Downloads folder", "category": "primary"},
            {"path": home / "OneDrive", "description": "OneDrive sync folder", "category": "cloud"},
            {"path": home / "OneDrive" / "Documents", "description": "OneDrive Documents", "category": "cloud"},
            {"path": Path("C:\\") / "Users" / "Public" / "Documents", "description": "Public Documents", "category": "shared"},
            {"path": home / "Google Drive", "description": "Google Drive folder", "category": "cloud"},
            {"path": home / "Dropbox", "description": "Dropbox folder", "category": "cloud"},
        ])
    elif system == "Darwin":  # macOS
        common_paths.extend([
            {"path": home / "Documents", "description": "Documents folder", "category": "primary"},
            {"path": home / "Desktop", "description": "Desktop folder", "category": "primary"},
            {"path": home / "Downloads", "description": "Downloads folder", "category": "primary"},
            {"path": home / "Library" / "CloudStorage", "description": "iCloud and cloud storage", "category": "cloud"},
            {"path": home / "Google Drive", "description": "Google Drive folder", "category": "cloud"},
            {"path": home / "Dropbox", "description": "Dropbox folder", "category": "cloud"},
            {"path": Path("/Users/Shared"), "description": "Shared folder", "category": "shared"},
        ])
    else:  # Linux
        common_paths.extend([
            {"path": home / "Documents", "description": "Documents folder", "category": "primary"},
            {"path": home / "Desktop", "description": "Desktop folder", "category": "primary"},
            {"path": home / "Downloads", "description": "Downloads folder", "category": "primary"},
            {"path": home / "Dropbox", "description": "Dropbox folder", "category": "cloud"},
            {"path": home / "Google Drive", "description": "Google Drive folder", "category": "cloud"},
            {"path": Path("/media"), "description": "External media", "category": "external"},
            {"path": Path("/mnt"), "description": "Mounted drives", "category": "external"},
        ])
    
    # Add work/project directories if they exist
    work_dirs = [
        home / "Work",
        home / "Projects",
        home / "workspace",
        home / "repos",
        home / "School",
        home / "University",
    ]
    
    for work_dir in work_dirs:
        if work_dir.exists():
            common_paths.append({
                "path": work_dir,
                "description": f"{work_dir.name} directory",
                "category": "work"
            })
    
    # Check each path and get quick stats
    converter = FileConverter()
    for path_info in common_paths:
        path = path_info["path"]
        if path.exists() and path.is_dir():
            try:
                # Quick count of documents (non-recursive)
                doc_count = 0
                total_size = 0
                
                for item in path.iterdir():
                    if item.is_file():
                        if item.suffix.lower() == '.pdf' or converter.is_supported(str(item)):
                            doc_count += 1
                            try:
                                total_size += item.stat().st_size
                            except:
                                pass
                
                recommendation = {
                    "path": str(path),
                    "exists": True,
                    "description": path_info["description"],
                    "category": path_info["category"],
                    "immediate_docs": doc_count,
                    "immediate_size_mb": total_size / (1024 * 1024) if total_size > 0 else 0,
                    "is_cloud": path_info["category"] == "cloud",
                    "is_primary": path_info["category"] == "primary"
                }
                
                # Estimate subdirectory count for recursion depth
                try:
                    subdir_count = sum(1 for item in path.iterdir() if item.is_dir())
                    recommendation["subdirs"] = subdir_count
                except:
                    recommendation["subdirs"] = 0
                
                recommendations.append(recommendation)
                
            except PermissionError:
                continue
            except Exception:
                continue
    
    # Sort recommendations by priority
    def sort_key(rec):
        # Primary folders first, then by document count
        priority = 0
        if rec["is_primary"]:
            priority = 1000
        elif rec["category"] == "work":
            priority = 500
        elif rec["is_cloud"]:
            priority = 300
        
        return -(priority + rec["immediate_docs"])
    
    recommendations.sort(key=sort_key)
    
    return recommendations

def analyze_path_for_search(path: str) -> Dict[str, Any]:
    """
    Analyze a specific path to estimate search complexity and time.
    """
    try:
        target_path = Path(path).expanduser().resolve()
        
        if not target_path.exists():
            return {"error": "Path does not exist"}
        
        if not target_path.is_dir():
            return {"error": "Path is not a directory"}
        
        # Quick analysis
        converter = FileConverter()
        stats = {
            "path": str(target_path),
            "total_items": 0,
            "total_dirs": 0,
            "immediate_docs": 0,
            "estimated_total_docs": 0,
            "max_depth": 0,
            "has_many_subdirs": False
        }
        
        # Sample the directory structure (limited depth)
        def sample_dir(path, depth=0, max_depth=3):
            if depth > max_depth:
                return
            
            try:
                items = list(path.iterdir())
                stats["total_items"] += len(items)
                
                for item in items[:100]:  # Sample first 100 items
                    if item.is_dir():
                        stats["total_dirs"] += 1
                        if depth < max_depth:
                            sample_dir(item, depth + 1, max_depth)
                    elif item.is_file():
                        if item.suffix.lower() == '.pdf' or converter.is_supported(str(item)):
                            if depth == 0:
                                stats["immediate_docs"] += 1
                            stats["estimated_total_docs"] += 1
            except:
                pass
        
        sample_dir(target_path)
        
        # Estimate search time
        estimated_time = stats["total_items"] * 0.01  # ~10ms per item
        
        return {
            "path": str(target_path),
            "analysis": {
                "immediate_documents": stats["immediate_docs"],
                "estimated_total_documents": stats["estimated_total_docs"],
                "subdirectories": stats["total_dirs"],
                "estimated_search_seconds": round(estimated_time, 1),
                "complexity": "high" if stats["total_dirs"] > 100 else "medium" if stats["total_dirs"] > 20 else "low"
            },
            "recommendation": "Good starting point" if stats["immediate_docs"] > 0 else "Consider a more specific path"
        }
        
    except Exception as e:
        return {"error": str(e)}

def search_files_in_path(
    start_path: str = None,
    extensions: List[str] = None,
    exclude_dirs: List[str] = None,
    max_results: int = 1000,
    min_size_kb: float = 0,
    max_size_mb: float = None,
    modified_after: str = None,
    search_term: str = None,
    show_progress: bool = True
) -> Dict[str, Any]:
    """
    Search for documents recursively from a starting path.
    
    Args:
        start_path: Starting directory path (default: user's home directory)
        extensions: List of file extensions to search for (default: all supported)
        exclude_dirs: List of directory names to exclude (default: common system dirs)
        max_results: Maximum number of results to return
        min_size_kb: Minimum file size in KB
        max_size_mb: Maximum file size in MB
        modified_after: ISO date string for filtering by modification date
        search_term: Search term to filter filenames
        show_progress: Whether to show progress during search
    
    Returns:
        Dictionary with search results and statistics
    """
    global search_in_progress, search_stop_flag
    
    if search_in_progress:
        return {
            "error": "Another search is already in progress",
            "status": "busy"
        }
    
    search_in_progress = True
    search_stop_flag = False
    
    try:
        # Setup start path
        if start_path:
            search_root = Path(start_path).expanduser().resolve()
        else:
            # Default to user's home directory
            search_root = Path.home()
        
        if not search_root.exists():
            return {
                "error": f"Start path does not exist: {search_root}",
                "status": "error"
            }
        
        # Setup file extensions
        converter = FileConverter()
        if extensions:
            # Validate extensions
            valid_extensions = []
            for ext in extensions:
                ext = ext.lower()
                if not ext.startswith('.'):
                    ext = '.' + ext
                if ext in converter.SUPPORTED_FORMATS or ext == '.pdf':
                    valid_extensions.append(ext)
        else:
            # Use all supported extensions
            valid_extensions = list(converter.SUPPORTED_FORMATS.keys()) + ['.pdf']
        
        # Setup excluded directories
        if exclude_dirs is None:
            # Default exclusions based on OS
            if platform.system() == "Windows":
                exclude_dirs = [
                    "$Recycle.Bin", "System Volume Information", "Windows",
                    "Program Files", "Program Files (x86)", "ProgramData",
                    "AppData", "Recovery", ".git", "__pycache__", "node_modules"
                ]
            else:  # macOS and Linux
                exclude_dirs = [
                    ".Trash", "Library", "Applications", ".git", "__pycache__",
                    "node_modules", ".cache", ".local", ".config", "snap",
                    ".npm", ".docker", ".vscode", "__MACOSX"
                ]
        
        # Parse date filter
        date_filter = None
        if modified_after:
            try:
                date_filter = datetime.fromisoformat(modified_after)
            except ValueError:
                return {
                    "error": f"Invalid date format: {modified_after}. Use ISO format (YYYY-MM-DD)",
                    "status": "error"
                }
        
        # Search statistics
        stats = {
            "total_files_scanned": 0,
            "total_dirs_scanned": 0,
            "skipped_dirs": 0,
            "errors": 0,
            "start_time": datetime.now()
        }
        
        # Results
        results = []
        dirs_processed = set()
        
        # Progress tracking
        last_progress_time = time.time()
        
        def should_exclude_dir(dir_name: str) -> bool:
            """Check if directory should be excluded."""
            dir_lower = dir_name.lower()
            for exclude in exclude_dirs:
                if exclude.lower() in dir_lower:
                    return True
            return False
        
        def search_directory(directory: Path):
            """Recursively search a directory."""
            nonlocal results, stats, last_progress_time
            
            if search_stop_flag:
                return
            
            if len(results) >= max_results:
                return
            
            # Skip if already processed
            try:
                dir_resolved = directory.resolve()
                if dir_resolved in dirs_processed:
                    return
                dirs_processed.add(dir_resolved)
            except Exception:
                stats["errors"] += 1
                return
            
            # Show progress
            if show_progress and time.time() - last_progress_time > 1:
                print(f"Searching... Dirs: {stats['total_dirs_scanned']}, Files: {len(results)}", file=sys.stderr)
                last_progress_time = time.time()
            
            try:
                # List directory contents
                items = list(directory.iterdir())
                stats["total_dirs_scanned"] += 1
                
                # Process files first
                for item in items:
                    if search_stop_flag or len(results) >= max_results:
                        break
                    
                    if item.is_file():
                        stats["total_files_scanned"] += 1
                        
                        # Check extension
                        if item.suffix.lower() not in valid_extensions:
                            continue
                        
                        # Apply filters
                        try:
                            file_stat = item.stat()
                            file_size_kb = file_stat.st_size / 1024
                            file_size_mb = file_size_kb / 1024
                            
                            # Size filters
                            if min_size_kb and file_size_kb < min_size_kb:
                                continue
                            if max_size_mb and file_size_mb > max_size_mb:
                                continue
                            
                            # Date filter
                            if date_filter:
                                mod_time = datetime.fromtimestamp(file_stat.st_mtime)
                                if mod_time < date_filter:
                                    continue
                            
                            # Name filter
                            if search_term and search_term.lower() not in item.name.lower():
                                continue
                            
                            # Get file type
                            file_type = converter.SUPPORTED_FORMATS.get(
                                item.suffix.lower(),
                                "PDF" if item.suffix.lower() == '.pdf' else "Unknown"
                            )
                            
                            # Add to results
                            results.append({
                                "path": str(item),
                                "name": item.name,
                                "directory": str(item.parent),
                                "size_mb": file_size_mb,
                                "type": file_type,
                                "modified": datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
                                "extension": item.suffix.lower()
                            })
                            
                        except Exception as e:
                            stats["errors"] += 1
                
                # Then process subdirectories
                for item in items:
                    if search_stop_flag or len(results) >= max_results:
                        break
                    
                    if item.is_dir():
                        # Check if should exclude
                        if should_exclude_dir(item.name):
                            stats["skipped_dirs"] += 1
                            continue
                        
                        # Recurse into subdirectory
                        search_directory(item)
                        
            except PermissionError:
                stats["errors"] += 1
                stats["skipped_dirs"] += 1
            except Exception as e:
                stats["errors"] += 1
        
        # Start search
        print(f"Starting document search from: {search_root}", file=sys.stderr)
        search_directory(search_root)
        
        # Calculate statistics
        elapsed_time = (datetime.now() - stats["start_time"]).total_seconds()
        
        # Sort results by modification date (newest first)
        results.sort(key=lambda x: x["modified"], reverse=True)
        
        # Cache results
        cache_key = f"{search_root}_{datetime.now().isoformat()}"
        search_results_cache[cache_key] = results
        
        return {
            "status": "completed" if not search_stop_flag else "stopped",
            "start_path": str(search_root),
            "results": results,
            "total_found": len(results),
            "statistics": {
                "dirs_scanned": stats["total_dirs_scanned"],
                "files_scanned": stats["total_files_scanned"],
                "dirs_skipped": stats["skipped_dirs"],
                "errors": stats["errors"],
                "elapsed_seconds": elapsed_time,
                "files_per_second": stats["total_files_scanned"] / elapsed_time if elapsed_time > 0 else 0
            },
            "filters_applied": {
                "extensions": valid_extensions,
                "excluded_dirs": exclude_dirs,
                "min_size_kb": min_size_kb,
                "max_size_mb": max_size_mb,
                "modified_after": modified_after,
                "search_term": search_term
            },
            "cache_key": cache_key
        }
        
    finally:
        search_in_progress = False

def stop_document_search() -> Dict[str, str]:
    """Stop an ongoing document search."""
    global search_stop_flag
    
    if not search_in_progress:
        return {"status": "no_search", "message": "No search is currently in progress"}
    
    search_stop_flag = True
    return {"status": "stopping", "message": "Search stop requested. Results will be partial."}

def get_cached_search_results(cache_key: str) -> Dict[str, Any]:
    """Retrieve cached search results."""
    if cache_key not in search_results_cache:
        return {"error": "Cache key not found", "available_keys": list(search_results_cache.keys())[-5:]}
    
    results = search_results_cache[cache_key]
    return {
        "cache_key": cache_key,
        "total_results": len(results),
        "results": results
    }

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
                config = json.load(f)
                # Load visual analysis setting if saved
                if "visual_analysis_enabled" in config:
                    global visual_analysis_enabled
                    visual_analysis_enabled = config["visual_analysis_enabled"]
                return config
    except Exception as e:
        print(f"Warning: Could not load config: {e}", file=sys.stderr)
    return {}

def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to file."""
    try:
        # Save current visual analysis setting
        config["visual_analysis_enabled"] = visual_analysis_enabled
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

# Visual Analysis Control Functions
def set_visual_analysis(enabled: bool) -> Tuple[bool, str]:
    """Enable or disable visual analysis globally."""
    global visual_analysis_enabled
    

    if DISABLE_VISUAL_ANALYSIS and enabled:
        return False, "❌ Visual analysis is disabled by environment variable DOCSRAY_DISABLE_VISUALS"
    
    visual_analysis_enabled = enabled
    
    # Save to config
    config = load_config()
    config["visual_analysis_enabled"] = enabled
    save_config(config)
    
    status = "enabled" if enabled else "disabled"
    return True, f"✅ Visual analysis {status} globally"

def get_visual_analysis_status() -> Dict[str, Any]:
    """Get current visual analysis status and settings."""
    return {
        "enabled": visual_analysis_enabled,
        "fast_mode": FAST_MODE,
        "env_disabled": DISABLE_VISUAL_ANALYSIS,
        "can_enable": not DISABLE_VISUAL_ANALYSIS
    }

# Directory Management functions (keeping existing ones)
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
def process_pdf(pdf_path: str, analyze_visuals: bool = None) -> Tuple[List, List, List[str]]:
    """Process PDF and build search index, also return raw pages text."""
    pdf_basename = Path(pdf_path).stem
    
    # Use global setting if not specified
    if analyze_visuals is None:
        analyze_visuals = visual_analysis_enabled
    
    # Check cache first
    sections, chunk_index = _load_cache(pdf_basename)
    
    # We need to extract anyway to get pages_text for summarization
    print(f"Processing PDF: {pdf_path}", file=sys.stderr)
    if analyze_visuals:
        print(f"👁️ Visual analysis: Enabled", file=sys.stderr)
    else:
        print(f"👁️ Visual analysis: Disabled", file=sys.stderr)
    
    def _do_extract():
        return pdf_extractor.extract_content(pdf_path, analyze_visuals=analyze_visuals)
    
    extracted = _do_extract()
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

# Unified summary system - replace the existing functions

def generate_and_save_summary(
    sections: List, 
    chunk_index: List, 
    doc_name: str,
    detail_level: str = "brief"
) -> Tuple[str, Optional[np.ndarray]]:
    """
    Generate summary using existing summarize_document_by_sections logic
    and save with embedding
    
    Returns:
        (summary_text, embedding_vector)
    """
    # Use existing summary generation logic
    if detail_level == "brief":
        max_chunks = 3
        brief_mode = True
    elif detail_level == "detailed":
        max_chunks = 8
        brief_mode = False
    else:  # standard
        max_chunks = 5
        brief_mode = False
    
    # Generate summary using existing function
    summary = summarize_document_by_sections(
        sections, 
        chunk_index,
        max_chunks_per_section=max_chunks,
        brief_mode=brief_mode
    )
    
    # Generate embedding for the summary

    summary_embedding = embedding_model.get_embedding(summary, is_query=False)
    
    # Save summary
    summary_cache_path = CACHE_DIR / f"{Path(doc_name).stem}_summary_{detail_level}.txt"
    with open(summary_cache_path, 'w', encoding='utf-8') as f:
        f.write(summary)
    
    # Save embedding
    embedding_cache_path = CACHE_DIR / f"{Path(doc_name).stem}_summary_{detail_level}_embedding.pkl"
    with open(embedding_cache_path, 'wb') as f:
        pickle.dump({
            "summary": summary,
            "embedding": summary_embedding.tolist(),
            "detail_level": detail_level,
            "doc_name": doc_name
        }, f)
    
    return summary, summary_embedding
def load_document_by_summary_search(
    query: str,
    folder_path: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Search for a document by query and load the best match
    
    Args:
        query: Search query
        folder_path: Directory to search (default: current folder)
    
    Returns:
        (success, message)
    """
    global current_sections, current_index, current_pdf_name, current_pages_text
    
    # Search documents
    search_results = search_by_content(query, folder_path, detail_level="brief", top_k=1)
    
    if not search_results["results"]:
        return False, "No documents found matching the query"
    
    # Get best match
    best_match = search_results["results"][0]
    doc_name = best_match["document"]
    similarity = best_match["similarity"]
    
    # Find the document file
    if folder_path:
        target_dir = Path(folder_path).expanduser().resolve()
    else:
        target_dir = current_pdf_folder
    
    # Look for the document
    converter = FileConverter()
    doc_path = None
    
    for file_path in target_dir.iterdir():
        if file_path.is_file() and file_path.stem == doc_name:
            if converter.is_supported(str(file_path)):
                doc_path = file_path
                break
    
    if not doc_path:
        return False, f"Document file not found: {doc_name}"
    
    # Load the document
    try:
        sections, chunk_index, pages_text = process_pdf(str(doc_path), analyze_visuals=False)
        
        current_sections = sections
        current_index = chunk_index
        current_pdf_name = doc_path.name
        current_pages_text = pages_text
        
        return True, f"✅ Loaded best matching document: {doc_path.name}\n📊 Similarity score: {similarity:.3f}\n📄 Summary preview: {best_match['summary'][:200]}..."
        
    except Exception as e:
        return False, f"Failed to load document: {str(e)}"
    
def process_all_documents(
    folder_path: Optional[str] = None,
    analyze_visuals: Optional[bool] = None,
    generate_summaries: bool = True,
    detail_level: str = "brief",
    extensions: Optional[List[str]] = None,
    max_files: Optional[int] = None
) -> Dict[str, Any]:
    """
    Process all documents in a directory with unified summary generation
    
    Args:
        folder_path: Directory path to process (default: current folder)
        analyze_visuals: Whether to analyze visual content (default: global setting)
        generate_summaries: Whether to generate summaries
        detail_level: Summary detail level ("brief", "standard", "detailed")
        extensions: List of file extensions to process (default: all supported)
        max_files: Maximum number of files to process
    
    Returns:
        Processing results
    """
    global current_sections, current_index, current_pdf_name, current_pages_text
    
    # Set target directory
    if folder_path:
        target_dir = Path(folder_path).expanduser().resolve()
    else:
        target_dir = current_pdf_folder
    
    if not target_dir.exists() or not target_dir.is_dir():
        return {"error": f"Invalid directory: {target_dir}"}
    
    # Visual analysis setting
    if analyze_visuals is None:
        analyze_visuals = visual_analysis_enabled
    
    # File extension setup
    converter = FileConverter()
    if extensions:
        valid_extensions = []
        for ext in extensions:
            ext = ext.lower()
            if not ext.startswith('.'):
                ext = '.' + ext
            if ext in converter.SUPPORTED_FORMATS or ext == '.pdf':
                valid_extensions.append(ext)
    else:
        valid_extensions = list(converter.SUPPORTED_FORMATS.keys()) + ['.pdf']
    
    # Define patterns for files to skip
    SKIP_PATTERNS = [
        'recovery-codes', 
        'recovery_codes',
        'password',
        'secret',
        'private-key',
        'private_key',
        'credentials',
        'api-key',
        'api_key',
        'token'
    ]
    # Find documents
    documents = []
    skipped_sensitive = []
    for file_path in sorted(target_dir.iterdir()):
        if file_path.is_file() and file_path.suffix.lower() in valid_extensions:
            file_name_lower = file_path.name.lower()
            if any(pattern in file_name_lower for pattern in SKIP_PATTERNS):
                print(f"⏭️  Skipping sensitive file: {file_path.name}", file=sys.stderr)
                skipped_sensitive.append(file_path.name)
                continue
            documents.append({
                "path": str(file_path),
                "name": file_path.name,
                "type": converter.SUPPORTED_FORMATS.get(
                    file_path.suffix.lower(),
                    "PDF" if file_path.suffix.lower() == '.pdf' else "Unknown"
                ),
                "size_mb": file_path.stat().st_size / (1024 * 1024)
            })
    
    # Limit file count
    if max_files and len(documents) > max_files:
        documents = documents[:max_files]
    
    # Process documents
    processed = []
    failed = []
    start_time = time.time()
    
    print(f"🚀 Starting batch processing of {len(documents)} documents...", file=sys.stderr)
    print(f"📊 Summary detail level: {detail_level}", file=sys.stderr)
    
    for i, doc in enumerate(documents):
        doc_path = doc["path"]
        doc_name = doc["name"]
        doc_stem = Path(doc_name).stem
        
        print(f"📄 [{i+1}/{len(documents)}] Processing {doc_name}...", file=sys.stderr)
        
        try:
            # Check if already processed with same detail level
            summary_cache_path = CACHE_DIR / f"{doc_stem}_summary_{detail_level}.txt"
            embedding_cache_path = CACHE_DIR / f"{doc_stem}_summary_{detail_level}_embedding.pkl"
            
            if summary_cache_path.exists() and embedding_cache_path.exists():
                print(f"⏭️  Using cached summary for {doc_name}", file=sys.stderr)
                processed.append({
                    "name": doc_name,
                    "sections": "cached",
                    "chunks": "cached",
                    "has_summary": True,
                    "cached": True
                })
                continue
            
            # Process document
            sections, chunk_index, pages_text = process_pdf(
                doc_path,
                analyze_visuals=analyze_visuals
            )
            
            # Store in global state temporarily for summary generation
            temp_current_pdf_name = current_pdf_name
            current_pdf_name = doc_stem
            
            # Generate summary if requested
            if generate_summaries:
                print(f"📝 Generating {detail_level} summary for {doc_name}...", file=sys.stderr)
                summary, embedding = generate_and_save_summary(
                    sections, 
                    chunk_index, 
                    doc_name,
                    detail_level
                )
            
            # Restore global state
            current_pdf_name = temp_current_pdf_name
            
            processed.append({
                "name": doc_name,
                "sections": len(sections),
                "chunks": len(chunk_index),
                "has_summary": generate_summaries,
                "cached": False
            })
            
            print(f"✅ Successfully processed {doc_name}", file=sys.stderr)
            
        except Exception as e:
            print(f"❌ Failed to process {doc_name}: {str(e)}", file=sys.stderr)
            failed.append({
                "name": doc_name,
                "error": str(e)
            })
    
    elapsed_time = time.time() - start_time
    
    # Set last processed document as current
    if processed and documents:
        last_doc = documents[-1]
        try:
            sections, chunk_index, pages_text = process_pdf(
                last_doc["path"],
                analyze_visuals=False  # Fast load
            )
            current_sections = sections
            current_index = chunk_index
            current_pdf_name = last_doc["name"]
            current_pages_text = pages_text
        except:
            pass
    
    return {
        "status": "completed",
        "folder": str(target_dir),
        "total_files": len(documents),
        "processed": len(processed),
        "failed": len(failed),
        "elapsed_time": elapsed_time,
        "processed_files": processed,
        "failed_files": failed,
        "current_document": current_pdf_name,
        "summaries_generated": generate_summaries,
        "detail_level": detail_level
    }

def search_by_content(
    query: str,
    folder_path: Optional[str] = None,
    detail_level: str = "brief",
    top_k: int = 5
) -> Dict[str, Any]:
    """
    Search documents based on their summary embeddings using optimized vector search
    
    Args:
        query: Search query
        folder_path: Directory to search (default: current folder)
        detail_level: Which summary level to search ("brief", "standard", "detailed")
        top_k: Number of top results to return
    
    Returns:
        Search results with similarity scores
    """
    # Set target directory
    if folder_path:
        target_dir = Path(folder_path).expanduser().resolve()
    else:
        target_dir = current_pdf_folder
    
    # Get query embedding
    query_embedding = embedding_model.get_embedding(query, is_query=True)
    pattern = f"*_summary_{detail_level}_embedding.pkl"
    embedding_files = list(CACHE_DIR.glob(pattern))    

    
    # Find all summary embeddings of the specified detail level

    if not embedding_files:
        all_pkl_files = list(CACHE_DIR.glob("*.pkl"))
        print(f"❓ All .pkl files in cache: {[f.name for f in all_pkl_files]}", file=sys.stderr)
        return {
            "query": query,
            "detail_level": detail_level,
            "total_documents": 0,
            "results": []
        }
    
    # Load all embeddings and metadata
    embeddings = []
    metadata = []
    
    for embedding_file in embedding_files:
        try:
            with open(embedding_file, 'rb') as f:
                data = pickle.load(f)
            
            # Extract document name
            doc_name = embedding_file.stem.replace(f"_summary_{detail_level}_embedding", "")
            
            embeddings.append(data["embedding"])
            metadata.append({
                "document": doc_name,
                "summary": data["summary"],
                "detail_level": data.get("detail_level", detail_level)
            })
        except Exception as e:
            print(f"Error reading embedding for {embedding_file.name}: {e}", file=sys.stderr)
            continue
    
    if not embeddings:
        return {
            "query": query,
            "detail_level": detail_level,
            "total_documents": 0,
            "results": []
        }
    
    # First search with original query
    results_with_scores = vector_search_with_metadata(
        query_emb=query_embedding,
        embeddings=embeddings,
        metadata=metadata,
        top_k=top_k
    )
    
    # Check if we need to improve the query
    if results_with_scores:
        # Get the best score
        best_score = results_with_scores[0][1]
        
        # If best score is low, try to improve the query
        if best_score < 0.7:  # Threshold for considering query improvement
            print(f"🔄 Best score {best_score:.3f} is low, improving query...", file=sys.stderr)
            
            # Use local LLM to improve the query
            improve_prompt = f"""Given the search query: "{query}"

Generate 3 alternative search queries that might find relevant documents. 
Consider synonyms, related terms, and different phrasings.
Return only the queries, one per line.

Alternative queries:"""
            
            try:
                improved_queries_response = local_llm_large.generate(improve_prompt)
                improved_queries = local_llm.strip_response(improved_queries_response).strip().split('\n')
                improved_queries = [query + ':' +q.strip() for q in improved_queries if q.strip()][:3]
                
                print(f"🔍 Trying improved queries: {improved_queries}", file=sys.stderr)
                
                # Search with each improved query
                all_results = list(results_with_scores)  # Keep original results
                seen_docs = {meta["document"] for meta, _ in results_with_scores}
                
                for improved_query in improved_queries:
                    # Get embedding for improved query
                    improved_embedding = embedding_model.get_embedding(improved_query, is_query=True)
                    
                    # Search with improved query
                    improved_results = vector_search_with_metadata(
                        query_emb=improved_embedding,
                        embeddings=embeddings,
                        metadata=metadata,
                        top_k=top_k
                    )
                    
                    # Add new results (avoid duplicates)
                    for meta, score in improved_results:
                        if meta["document"] not in seen_docs:
                            all_results.append((meta, score * 0.9))  # Slightly penalize improved query results
                            seen_docs.add(meta["document"])
                
                # Re-sort all results by score
                all_results.sort(key=lambda x: x[1], reverse=True)
                results_with_scores = all_results[:top_k]
                
            except Exception as e:
                print(f"Error improving query: {e}", file=sys.stderr)
                # Continue with original results
    # Format results
    results = []
    for meta, score in results_with_scores:
        results.append({
            "document": meta["document"],
            "similarity": score,
            "summary": meta["summary"],
            "detail_level": meta["detail_level"]
        })
    
    return {
        "query": query,
        "detail_level": detail_level,
        "total_documents": len(embeddings),
        "results": results
    }

def get_document_summaries(
    folder_path: Optional[str] = None,
    detail_level: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get all document summaries in a directory
    
    Args:
        folder_path: Directory path (default: current folder)
        detail_level: Filter by detail level (optional)
    
    Returns:
        Dictionary with all summaries
    """
    # Set target directory
    if folder_path:
        target_dir = Path(folder_path).expanduser().resolve()
    else:
        target_dir = current_pdf_folder
    
    summaries = []
    
    # Find all summary files
    if detail_level:
        pattern = f"*_summary_{detail_level}.txt"
    else:
        pattern = "*_summary_*.txt"
    
    for summary_file in CACHE_DIR.glob(pattern):
        try:
            # Extract info from filename
            stem = summary_file.stem
            parts = stem.split("_summary_")
            if len(parts) == 2:
                doc_name = parts[0]
                file_detail_level = parts[1]
            else:
                continue
            
            # Skip section summaries
            if "section_" in summary_file.name:
                continue
            
            # Read summary
            with open(summary_file, 'r', encoding='utf-8') as f:
                summary_text = f.read()
            
            # Check if embedding exists
            embedding_path = CACHE_DIR / f"{doc_name}_summary_{file_detail_level}_embedding.pkl"
            has_embedding = embedding_path.exists()
            
            summaries.append({
                "document": doc_name,
                "summary": summary_text,
                "detail_level": file_detail_level,
                "has_embedding": has_embedding
            })
            
        except Exception as e:
            print(f"Error reading summary for {summary_file.name}: {e}", file=sys.stderr)
            continue
    
    # Group by document
    docs_summary = {}
    for s in summaries:
        doc = s["document"]
        if doc not in docs_summary:
            docs_summary[doc] = {}
        docs_summary[doc][s["detail_level"]] = s
    
    return {
        "folder": str(target_dir),
        "total_documents": len(docs_summary),
        "summaries_by_document": docs_summary,
        "detail_level_filter": detail_level
    }

def summarize_document_by_sections(sections: List, chunk_index: List, 
                                   max_chunks_per_section: int = 5,
                                   brief_mode: bool = False) -> str:
    """
    Create a comprehensive summary of the document organized by sections.
    Overall summary at the top, no table of contents.
    """
    
    # Use smaller model for everything in fast mode
    if brief_mode:
        summary_model = local_llm
        overall_model = local_llm
    else:
        summary_model = local_llm
        overall_model = local_llm_large
    
    # Determine detail level for cache      
    if max_chunks_per_section <= 3:
        detail_level = "brief"
    elif max_chunks_per_section >= 8:
        detail_level = "detailed"
    else:
        detail_level = "standard"
    
    summary_parts = []
    summary_parts.append(f"# 📄 Document Summary: {current_pdf_name}\n")
    
    # Generate overall summary FIRST
    overall_cache_path = CACHE_DIR / f"{current_pdf_name}_overall_{detail_level}.txt"
    
    if overall_cache_path.exists():
        try:
            with open(overall_cache_path, 'r', encoding='utf-8') as f:
                overall_summary = f.read()
            summary_parts.append("## 🎯 Overall Summary\n")
            summary_parts.append(overall_summary)
            summary_parts.append("\n")
        except Exception:
            pass
    else:
        # Create overall summary
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
            
            summary_parts.append("## 🎯 Overall Summary\n")
            summary_parts.append(overall_summary)
            summary_parts.append("\n")
        except Exception as e:
            print(f"Error generating overall summary: {str(e)}", file=sys.stderr)
    
    # Section summaries
    summary_parts.append("## 📊 Section Details\n")
    
    # Process all sections at once
    for i, section in enumerate(sections):
        cache_path = _section_cache_path(current_pdf_name, i, detail_level)
        
        if cache_path.exists():
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    section_summary = f.read()
                summary_parts.append(section_summary)
                summary_parts.append("")
                continue
            except Exception:
                pass
        
        # Generate section summary
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
            # Select chunks based on mode
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
            
            # Combine chunk contents
            combined_content = "\n".join([
                chunk["metadata"].get("content", "")[:500 if brief_mode else 1000]
                for chunk in selected_chunks
            ])
            
            # Generate summary
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
                summary_text = summary_model.strip_response(summary_response)
                elapsed = time.time() - start_time
                print(f"Section {i+1} summarized in {elapsed:.1f}s", file=sys.stderr)
            except Exception as e:
                summary_text = f"*Error generating summary: {str(e)}*"
        
        # Format section summary
        section_summary = f"### {i+1}. {title}\n*Pages {start_page}-{end_page}*\n\n{summary_text}"
        
        # Save to cache
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                f.write(section_summary)
            print(f"Section {i+1} saved to cache", file=sys.stderr)
        except Exception as e:
            print(f"Failed to cache section {i+1}: {e}", file=sys.stderr)
        
        summary_parts.append(section_summary)
        summary_parts.append("")
    
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
                        "description": "Whether to analyze visual content (default: uses global setting)",
                        "default": None
                    }
                },
                "required": ["filename"]
            }
        ),
        Tool(
            name="set_visual_analysis",
            description="Enable or disable visual analysis globally for all documents",
            inputSchema={
                "type": "object",
                "properties": {
                    "enabled": {"type": "boolean", "description": "Enable (true) or disable (false) visual analysis"}
                },
                "required": ["enabled"]
            }
        ),
        Tool(
            name="get_visual_analysis_status",
            description="Get current visual analysis settings and status",
            inputSchema={
                "type": "object",
                "properties": {}
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
        ),
        Tool(
            name="get_recommended_search_paths",
            description="Get recommended starting paths for document search based on your OS and common locations",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="analyze_search_path",
            description="Analyze a specific path to estimate search complexity and document count",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to analyze"}
                },
                "required": ["path"]
            }
        ),
        Tool(
            name="search_documents",
            description="Search for documents recursively from a starting path with various filters",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_path": {"type": "string", "description": "Starting directory path (optional, defaults to home)"},
                    "extensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "File extensions to search for (e.g., ['pdf', 'docx'])"
                    },
                    "exclude_dirs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Directory names to exclude from search"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return",
                        "default": 1000
                    },
                    "min_size_kb": {
                        "type": "number",
                        "description": "Minimum file size in KB"
                    },
                    "max_size_mb": {
                        "type": "number",
                        "description": "Maximum file size in MB"
                    },
                    "modified_after": {
                        "type": "string",
                        "description": "ISO date string (YYYY-MM-DD) to filter files modified after this date"
                    },
                    "search_term": {
                        "type": "string",
                        "description": "Search term to filter filenames"
                    }
                }
            }
        ),
        Tool(
            name="process_all_documents",
            description="Process all documents in the current or specified directory at once, with optional summary generation",
            inputSchema={
                "type": "object",
                "properties": {
                    "folder_path": {
                        "type": "string", 
                        "description": "Directory path to process (optional, uses current if not specified)"
                    },
                                "detail_level": {
                "type": "string",
                "description": "Summary detail level: 'brief', 'standard', or 'detailed'",
                "enum": ["brief", "standard", "detailed"],
                "default": "brief"
            },
                    "analyze_visuals": {
                        "type": "boolean",
                        "description": "Whether to analyze visual content (default: uses global setting)"
                    },
                    "generate_summaries": {
                        "type": "boolean",
                        "description": "Whether to generate summaries with embeddings for each document",
                        "default": True
                    },
                    "extensions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "File extensions to process (e.g., ['pdf', 'docx'])"
                    },
                    "max_files": {
                        "type": "integer",
                        "description": "Maximum number of files to process"
                    }
                }
            }
        ),

        Tool(
            name="search_by_content",
            description="Search for documents using their summary embeddings",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query to find relevant documents"
                    },
                    "folder_path": {
                        "type": "string",
                        "description": "Directory to search (optional, uses current if not specified)"
                    },
                    "detail_level": {
                        "type": "string",
                        "description": "Which summary level to search",
                        "enum": ["brief", "standard", "detailed"],
                        "default": "brief"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of top results to return",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        ),

        Tool(
            name="load_document_by_summary_search",
            description="Search for a document by query and automatically load the best match",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query to find and load the most relevant document"
                    },
                    "folder_path": {
                        "type": "string",
                        "description": "Directory to search (optional, uses current if not specified)"
                    }
                },
                "required": ["query"]
            }
        ),

        Tool(
            name="get_document_summaries",
            description="Get all document summaries in the current or specified directory",
            inputSchema={
                "type": "object",
                "properties": {
                    "folder_path": {
                        "type": "string",
                        "description": "Directory path (optional, uses current if not specified)"
                    },
                    "detail_level": {
                "type": "string",
                "description": "Filter by detail level (optional)",
                "enum": ["brief", "standard", "detailed"]
            }
                }
            }
        ),        
        Tool(
            name="stop_search",
            description="Stop an ongoing document search",
            inputSchema={
                "type": "object",
                "properties": {}
            }
        ),
        Tool(
            name="get_search_results",
            description="Retrieve cached search results using a cache key",
            inputSchema={
                "type": "object",
                "properties": {
                    "cache_key": {"type": "string", "description": "Cache key from a previous search"}
                },
                "required": ["cache_key"]
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
            analyze_visuals = arguments.get("analyze_visuals")
            
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
            
            # Process the document
            #try:
            from docsray.scripts import pdf_extractor
            
            # Use global setting if not specified
            if analyze_visuals is None:
                analyze_visuals = visual_analysis_enabled
            
            # Extract content with visual analysis option
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
            
            response += f"👁️ Visual analysis: {'Enabled' if analyze_visuals else 'Disabled'}\n"
            response += f"📊 File size: {file_size:.1f} MB\n"
            response += f"📄 Pages: {num_pages}\n"
            response += f"📑 Sections: {num_sections}\n"
            response += f"🔍 Chunks: {num_chunks}\n\n"
            response += "You can now:\n"
            response += "• Ask questions about this document using 'ask_question'\n"
            response += "• Generate a comprehensive summary using 'summarize_document'"
            
            return [TextContent(type="text", text=response)]

            #except Exception as e:
            #    return [TextContent(type="text", text=f"❌ Error processing document: {str(e)}")]
        
        elif name == "set_visual_analysis":
            enabled = arguments["enabled"]
            success, message = set_visual_analysis(enabled)
            
            if success:
                # Add status information
                status = get_visual_analysis_status()
                response = f"{message}\n\n"
                response += f"📊 **Current Settings:**\n"
                response += f"• Visual Analysis: {'✅ Enabled' if status['enabled'] else '❌ Disabled'}\n"
                response += f"• Fast Mode: {'Yes' if status['fast_mode'] else 'No'}\n"
                response += f"• Environment Override: {'Yes' if status['env_disabled'] else 'No'}\n"
            else:
                response = message
            
            return [TextContent(type="text", text=response)]
        
        elif name == "get_visual_analysis_status":
            status = get_visual_analysis_status()
            
            response = f"👁️ **Visual Analysis Status:**\n\n"
            response += f"• **Currently:** {'✅ Enabled' if status['enabled'] else '❌ Disabled'}\n"
            response += f"• **Fast Mode:** {'Yes (forced off)' if status['fast_mode'] else 'No'}\n"
            response += f"• **Environment Variable:** {'DOCSRAY_DISABLE_VISUALS=1 (forced off)' if status['env_disabled'] else 'Not set'}\n"
            response += f"• **Can Enable:** {'Yes' if status['can_enable'] else 'No'}\n\n"
            
            if not status['can_enable']:
                response += "⚠️ **Note:** Visual analysis cannot be enabled due to:\n"
                if status['env_disabled']:
                    response += "• DOCSRAY_DISABLE_VISUALS environment variable is set\n"
            else:
                response += "💡 **Tip:** Use 'set_visual_analysis' to toggle this setting."
            
            return [TextContent(type="text", text=response)]
             
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
            
            # Generate and save summary with embedding
            response = f"📄 **Generating {detail_level} summary for:** {current_pdf_name}\n"
            
            try:
                start_time = time.time()
                
                summary, embedding = generate_and_save_summary(
                    current_sections,
                    current_index,
                    current_pdf_name,
                    detail_level
                )
                
                elapsed = time.time() - start_time
                
                response += f"⏱️ Generated in {elapsed:.1f} seconds\n"
                response += f"✅ Summary saved with embedding\n\n"
                response += summary
                
            except Exception as e:
                response += f"❌ Error generating summary: {str(e)}"
            
            return [TextContent(type="text", text=response)]

        elif name == "process_all_documents":
            folder_path = arguments.get("folder_path")
            analyze_visuals = arguments.get("analyze_visuals")
            generate_summaries = arguments.get("generate_summaries", True)
            detail_level = arguments.get("detail_level", "brief")
            extensions = arguments.get("extensions")
            max_files = arguments.get("max_files")
            
            response = "🚀 **Batch Processing Documents**\n\n"
            
            # Process all documents
            result = process_all_documents(
                folder_path=folder_path,
                analyze_visuals=analyze_visuals,
                generate_summaries=generate_summaries,
                detail_level=detail_level,
                extensions=extensions,
                max_files=max_files
            )
            
            if "error" in result:
                return [TextContent(type="text", text=f"❌ Error: {result['error']}")]
            
            # Format results
            response += f"📁 Directory: {result['folder']}\n"
            response += f"📊 Total files found: {result['total_files']}\n"
            response += f"✅ Successfully processed: {result['processed']}\n"
            
            if result.get('skipped_sensitive', 0) > 0:
                response += f"⏭️  Skipped (sensitive): {result['skipped_sensitive']}\n"
            
            if result['failed'] > 0:
                response += f"❌ Failed: {result['failed']}\n"
            
            response += f"⏱️ Processing time: {result['elapsed_time']:.1f} seconds\n"
            
            if generate_summaries:
                response += f"📝 Summary level: {detail_level}\n"
            
            # Show processed files
            if result['processed_files']:
                response += "\n**Processed Files:**\n"
                for doc in result['processed_files'][:10]:  # Show first 10
                    response += f"• {doc['name']} "
                    if doc.get('cached'):
                        response += "(cached) "
                    else:
                        response += f"({doc['sections']} sections, {doc['chunks']} chunks) "
                    if doc['has_summary']:
                        response += "📝"
                    response += "\n"
                
                if len(result['processed_files']) > 10:
                    response += f"... and {len(result['processed_files']) - 10} more files\n"
            
            # Show skipped sensitive files
            if result.get('skipped_files'):
                response += "\n**Skipped Sensitive Files:**\n"
                for filename in result['skipped_files'][:5]:
                    response += f"• {filename} (contains sensitive keywords)\n"
                if len(result['skipped_files']) > 5:
                    response += f"... and {len(result['skipped_files']) - 5} more files\n"
            
            # Show failed files
            if result['failed_files']:
                response += "\n**Failed Files:**\n"
                for doc in result['failed_files'][:5]:
                    response += f"• {doc['name']}: {doc['error']}\n"
            
            if result['current_document']:
                response += f"\n📄 Current document set to: {result['current_document']}"
            
            response += "\n\n💡 You can now:\n"
            response += "• Use 'search_by_content' to find documents by content\n"
            response += "• Use 'load_document_by_summary_search' to quickly switch documents\n"
            response += "• Use 'ask_question' to query the current document"
            
            return [TextContent(type="text", text=response)]

        elif name == "search_by_content":
            query = arguments["query"]
            folder_path = arguments.get("folder_path")
            detail_level = arguments.get("detail_level", "brief")
            top_k = arguments.get("top_k", 5)
            
            result = search_by_content(query, folder_path, detail_level, top_k)
            
            response = f"🔍 **Document Search Results**\n\n"
            response += f"Query: \"{query}\"\n"
            response += f"Found: {result['total_documents']} documents with summaries\n\n"
            
            if result['results']:
                response += "**Top Results:**\n"
                for i, doc in enumerate(result['results'], 1):
                    response += f"\n{i}. **{doc['document']}**\n"
                    response += f"   📊 Similarity: {doc['similarity']:.3f}\n"
                    
                    # Show summary preview
                    summary_preview = doc['summary'].split('\n')[0:10]  # First 3 lines
                    response += "   📝 Summary preview:\n"
                    for line in summary_preview:
                        if line.strip():
                            response += f"      {line.strip()}\n"
                    response += "\n"
            else:
                response += "No documents found with summaries.\n"
                response += "💡 Run 'process_all_documents' first to generate summaries."
            
            return [TextContent(type="text", text=response)]

        elif name == "load_document_by_summary_search":
            query = arguments["query"]
            folder_path = arguments.get("folder_path")
            
            success, message = load_document_by_summary_search(query, folder_path)
            
            if success:
                response = f"🎯 **Document Loaded by Search**\n\n{message}"
            else:
                response = f"❌ **Search Failed**\n\n{message}"
            
            return [TextContent(type="text", text=response)]
        
        elif name == "get_document_summaries":
            folder_path = arguments.get("folder_path")
            detail_level = arguments.get("detail_level")
            
            result = get_document_summaries(folder_path, detail_level)
            
            response = f"📚 **Document Summaries**\n\n"
            response += f"📁 Directory: {result['folder']}\n"
            
            # Handle the new return format
            if "summaries_by_document" in result:
                docs_summary = result["summaries_by_document"]
                response += f"📝 Total documents with summaries: {result['total_documents']}\n"
                
                if result.get("detail_level_filter"):
                    response += f"🔍 Filtered by: {result['detail_level_filter']} level\n"
                
                response += "\n"
                
                if docs_summary:
                    for doc_name, levels in docs_summary.items():
                        response += f"**{doc_name}**\n"
                        
                        # Show available summary levels
                        available_levels = []
                        for level in ["brief", "standard", "detailed"]:
                            if level in levels:
                                if levels[level].get("has_embedding"):
                                    available_levels.append(f"{level} ✅")
                                else:
                                    available_levels.append(f"{level} ⚠️")
                        
                        if available_levels:
                            response += f"  Available: {', '.join(available_levels)}\n"
                        
                        # Show preview of the first available summary
                        preview_shown = False
                        for level in ["brief", "standard", "detailed"]:
                            if level in levels and not preview_shown:
                                summary_text = levels[level].get("summary", "")
                                summary_lines = summary_text.split('\n')[:3]
                                response += "  Preview:\n"
                                for line in summary_lines:
                                    if line.strip():
                                        response += f"    {line.strip()}\n"
                                preview_shown = True
                                break
                        
                        response += "\n"
                else:
                    response += "📭 No summaries found.\n"
                    response += "💡 Run 'process_all_documents' with generate_summaries=True"
            
            # Handle old format (backward compatibility)
            elif "summaries" in result:
                summaries = result["summaries"]
                response += f"📝 Total summaries: {len(summaries)}\n\n"
                
                if summaries:
                    for summary_info in summaries:
                        response += f"**{summary_info['document']}**"
                        if summary_info['has_embedding']:
                            response += " ✅"
                        else:
                            response += " ⚠️ (no embedding)"
                        response += f" [{summary_info.get('detail_level', 'unknown')}]\n"
                        
                        # Show first few lines of summary
                        summary_lines = summary_info['summary'].split('\n')[:3]
                        for line in summary_lines:
                            if line.strip():
                                response += f"  {line.strip()}\n"
                        response += "\n"
                else:
                    response += "No summaries found.\n"
                    response += "💡 Run 'process_all_documents' with generate_summaries=True"
            
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
        
        elif name == "get_recommended_search_paths":
            recommendations = get_recommended_search_paths()
            
            if not recommendations:
                return [TextContent(type="text", text="❌ No recommended paths found on your system")]
            
            response = "🔍 **Recommended Search Starting Points:**\n\n"
            
            # Group by category
            by_category = {}
            for rec in recommendations:
                cat = rec["category"]
                if cat not in by_category:
                    by_category[cat] = []
                by_category[cat].append(rec)
            
            # Display by category
            category_names = {
                "primary": "📁 Primary Folders",
                "cloud": "☁️ Cloud Storage",
                "work": "💼 Work/Projects",
                "shared": "👥 Shared Folders",
                "external": "💾 External Storage",
                "general": "🏠 General"
            }
            
            for category in ["primary", "work", "cloud", "shared", "external", "general"]:
                if category in by_category:
                    response += f"**{category_names.get(category, category.title())}:**\n"
                    
                    for rec in by_category[category]:
                        response += f"\n📍 **{rec['description']}**\n"
                        response += f"   Path: `{rec['path']}`\n"
                        
                        if rec['immediate_docs'] > 0:
                            response += f"   📄 {rec['immediate_docs']} documents found (immediate)\n"
                            response += f"   💾 {rec['immediate_size_mb']:.1f} MB\n"
                        
                        if rec['subdirs'] > 0:
                            response += f"   📂 {rec['subdirs']} subdirectories\n"
                        
                    response += "\n"
            
            response += "💡 **Tips:**\n"
            response += "• Use 'analyze_search_path' to get more details about a specific path\n"
            response += "• Primary folders are usually the best starting points\n"
            response += "• Cloud folders may take longer to search"
            
            return [TextContent(type="text", text=response)]

        elif name == "analyze_search_path":
            path = arguments["path"]
            analysis = analyze_path_for_search(path)
            
            if "error" in analysis:
                return [TextContent(type="text", text=f"❌ {analysis['error']}")]
            
            response = f"📊 **Path Analysis:**\n\n"
            response += f"📍 Path: `{analysis['path']}`\n\n"
            
            info = analysis["analysis"]
            response += f"**Quick Statistics:**\n"
            response += f"• 📄 Documents (immediate): {info['immediate_documents']}\n"
            response += f"• 📈 Estimated total documents: {info['estimated_total_documents']}\n"
            response += f"• 📂 Subdirectories: {info['subdirectories']}\n"
            response += f"• ⏱️ Estimated search time: {info['estimated_search_seconds']} seconds\n"
            response += f"• 🔍 Complexity: {info['complexity']}\n\n"
            
            response += f"**Recommendation:** {analysis['recommendation']}\n\n"
            
            if info['complexity'] == "high":
                response += "⚠️ **Note:** This path has many subdirectories. Consider:\n"
                response += "• Using more specific starting points\n"
                response += "• Setting stricter filters\n"
                response += "• Using 'exclude_dirs' to skip unnecessary folders"
            
            return [TextContent(type="text", text=response)]

        elif name == "search_documents":
            # Show search is starting
            start_path = arguments.get("start_path", str(Path.home()))
            
            response = "🔍 **Starting Document Search...**\n"
            response += f"📍 Starting from: `{start_path}`\n"
            response += "⏳ This may take a while depending on the directory size...\n\n"
            
            # Run search
            search_result = search_files_in_path(
                start_path=arguments.get("start_path"),
                extensions=arguments.get("extensions"),
                exclude_dirs=arguments.get("exclude_dirs"),
                max_results=arguments.get("max_results", 1000),
                min_size_kb=arguments.get("min_size_kb", 0),
                max_size_mb=arguments.get("max_size_mb"),
                modified_after=arguments.get("modified_after"),
                search_term=arguments.get("search_term"),
                show_progress=True
            )
            
            if "error" in search_result:
                return [TextContent(type="text", text=f"❌ Search error: {search_result['error']}")]
            
            # Format results
            response = f"✅ **Search {search_result['status'].title()}**\n\n"
            
            # Statistics
            stats = search_result["statistics"]
            response += f"**Search Statistics:**\n"
            response += f"• 📊 Files found: {search_result['total_found']}\n"
            response += f"• 📂 Directories scanned: {stats['dirs_scanned']}\n"
            response += f"• 📄 Files examined: {stats['files_scanned']}\n"
            response += f"• ⏱️ Time: {stats['elapsed_seconds']:.1f} seconds\n"
            response += f"• 🚀 Speed: {stats['files_per_second']:.1f} files/second\n\n"
            
            if search_result['total_found'] > 0:
                # Group results by type
                by_type = {}
                for doc in search_result['results']:
                    doc_type = doc['type']
                    if doc_type not in by_type:
                        by_type[doc_type] = []
                    by_type[doc_type].append(doc)
                
                response += "**Results by Type:**\n"
                for doc_type, docs in sorted(by_type.items()):
                    response += f"\n**{doc_type}** ({len(docs)} files):\n"
                    
                    # Show first 5 of each type
                    for i, doc in enumerate(docs[:5]):
                        response += f"{i+1}. {doc['name']}\n"
                        response += f"   📁 {doc['directory']}\n"
                        response += f"   💾 {doc['size_mb']:.1f} MB\n"
                        response += f"   📅 Modified: {doc['modified'][:10]}\n"
                    
                    if len(docs) > 5:
                        response += f"   ... and {len(docs) - 5} more {doc_type} files\n"
                
                response += f"\n💾 **Cache Key:** `{search_result['cache_key']}`\n"
                response += "💡 Use 'get_search_results' with this cache key to retrieve full results\n"
            else:
                response += "📭 No documents found matching your criteria.\n\n"
                response += "💡 Try:\n"
                response += "• Using a different starting path\n"
                response += "• Relaxing your search filters\n"
                response += "• Checking 'get_recommended_search_paths' for better locations"
            
            return [TextContent(type="text", text=response)]

        elif name == "stop_search":
            result = stop_document_search()
            
            if result["status"] == "no_search":
                response = "ℹ️ No search is currently running."
            else:
                response = "🛑 " + result["message"]
            
            return [TextContent(type="text", text=response)]

        elif name == "get_search_results":
            cache_key = arguments["cache_key"]
            result = get_cached_search_results(cache_key)
            
            if "error" in result:
                response = f"❌ {result['error']}\n\n"
                if result.get("available_keys"):
                    response += "Recent cache keys:\n"
                    for key in result["available_keys"]:
                        response += f"• `{key}`\n"
                return [TextContent(type="text", text=response)]
            
            # Format full results
            response = f"📋 **Cached Search Results**\n"
            response += f"Cache key: `{cache_key}`\n"
            response += f"Total results: {result['total_results']}\n\n"
            
            # Group by directory
            by_dir = {}
            for doc in result['results']:
                dir_path = doc['directory']
                if dir_path not in by_dir:
                    by_dir[dir_path] = []
                by_dir[dir_path].append(doc)
            
            # Show results organized by directory
            for dir_path, docs in sorted(by_dir.items()):
                response += f"\n📁 **{dir_path}**\n"
                for doc in docs:
                    response += f"  • {doc['name']} ({doc['type']}, {doc['size_mb']:.1f} MB)\n"
            
            response += f"\n💡 Use 'load_document' with the full path to process any of these files."
            
            return [TextContent(type="text", text=response)]
        else:
            return [TextContent(type="text", text=f"❌ Unknown tool: {name}")]
            
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return [TextContent(type="text", text=f"❌ Error: {str(e)}\n\nDetails:\n{error_details}")]

async def run_mcp_server():
    """Run the MCP server (async version)."""
    print(f"Starting DocsRay MCP Server (Enhanced with Visual Analysis Control)...", file=sys.stderr)
    print(f"Default PDF Folder: {DEFAULT_PDF_FOLDER}", file=sys.stderr)
    print(f"Current PDF Folder: {current_pdf_folder}", file=sys.stderr)
    print(f"Cache Directory: {CACHE_DIR}", file=sys.stderr)
    print(f"Config File: {CONFIG_FILE}", file=sys.stderr)
    print(f"Fast Mode: {'Enabled' if FAST_MODE else 'Disabled'}", file=sys.stderr)
    print(f"Visual Analysis: {'Enabled' if visual_analysis_enabled else 'Disabled'}", file=sys.stderr)
    
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