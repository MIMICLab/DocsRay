# web_demo.py - Enhanced version with auto-recovery and PDF timeout

import os
import shutil
from typing import Tuple, List, Optional, Dict
import tempfile
from pathlib import Path
import json
import uuid
import pickle
import time
import pathlib
import gradio as gr
import traceback
import logging
import gc
import psutil
from datetime import datetime
import threading
import queue
import sys
import concurrent.futures
import signal

from docsray.chatbot import PDFChatBot, DEFAULT_SYSTEM_PROMPT
from docsray.scripts import pdf_extractor, chunker, build_index, section_rep_builder
from docsray.scripts.file_converter import FileConverter

# Setup logging
log_dir = Path.home() / ".docsray" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / f"web_demo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# --- Liveness watchdog variables ---
LAST_ACTIVITY = time.time()           # Timestamp of last successful UI update
HEALTH_TIMEOUT = 300                 # Seconds of silence → watchdog restart

def safe_progress(cb, pct, msg):
    """
    Wrapper around Gradio progress callbacks that
    (1) updates global liveness,
    (2) swallows BrokenPipeError if the browser tab closed,
    (3) triggers auto‑recovery on lost connection.
    """
    global LAST_ACTIVITY
    LAST_ACTIVITY = time.time()
    if cb is None:
        return
    try:
        cb(pct, msg)
    except Exception:
        logger.error("Progress callback lost – BrokenPipe?")
        ErrorRecoveryMixin.trigger_recovery("broken_pipe")

# Create a temporary directory for this session
TEMP_DIR = Path(tempfile.gettempdir()) / "docsray_web"
TEMP_DIR.mkdir(exist_ok=True)

# Session timeout (24 hours)
SESSION_TIMEOUT = 86400
PAGE_LIMIT = 5
PDF_PROCESS_TIMEOUT = 300
# Error recovery settings
MAX_MEMORY_PERCENT = 90  # Restart if memory usage exceeds this
ERROR_THRESHOLD = 1  # Number of errors before restart
ERROR_WINDOW = 10 # Time window for error counting 

# Global error tracking
error_queue = queue.Queue()
error_times = []

class ProcessingTimeoutError(Exception):
    """Exception raised when document processing takes too long"""
    pass

class ErrorRecoveryMixin:
    """Mixin class for error recovery functionality"""
    
    @staticmethod
    def safe_execute(func, *args, **kwargs):
        """Execute function with error handling and recovery"""
        global error_times
        
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Log error
            error_msg = f"Error in {func.__name__}: {str(e)}\n{traceback.format_exc()}"
            logger.error(error_msg)
            
            # Track error
            current_time = time.time()
            error_times.append(current_time)
            
            # Clean old errors
            error_times = [t for t in error_times if current_time - t < ERROR_WINDOW]
            
            # Check if we need to trigger recovery
            if len(error_times) >= ERROR_THRESHOLD:
                logger.critical(f"Error threshold reached ({len(error_times)} errors in {ERROR_WINDOW}s)")
                ErrorRecoveryMixin.trigger_recovery("error_threshold")
            
            # Return safe default
            if func.__name__ == "load_document":
                return args[2], f"❌ Error processing document: {str(e)}", gr.update()
            elif func.__name__ == "ask_question":
                return f"❌ Error: {str(e)}", ""
            else:
                raise
    
    @staticmethod
    def check_memory():
        """Check memory usage and trigger recovery if needed"""
        try:
            memory_percent = psutil.virtual_memory().percent
            if memory_percent > MAX_MEMORY_PERCENT:
                logger.warning(f"High memory usage: {memory_percent}%")
                
                # Try garbage collection first
                gc.collect()
                
                # Check again
                memory_percent = psutil.virtual_memory().percent
                if memory_percent > MAX_MEMORY_PERCENT:
                    ErrorRecoveryMixin.trigger_recovery("high_memory")
                    
        except Exception as e:
            logger.error(f"Error checking memory: {e}")
    
    @staticmethod
    def trigger_recovery(reason):
        """Trigger recovery action - FIXED VERSION"""
        logger.critical(f"Triggering recovery due to: {reason}")
        
        try:
            # Clean up temporary files
            ErrorRecoveryMixin.cleanup_temp_files()
            
            # Force garbage collection
            gc.collect()
            
            # Log recovery
            with open(log_dir / "recovery_log.txt", "a") as f:
                f.write(f"{datetime.now()}: Recovery triggered - {reason}\n")
            
            # Check if running under auto-restart wrapper
            if os.environ.get('DOCSRAY_AUTO_RESTART') == '1':
                logger.info("Running under auto-restart wrapper, requesting restart...")
                # Exit with code 42 to signal restart request
                logging.shutdown()
                time.sleep(0.1)
                os._exit(42)
            else:
                logger.warning("Not running under auto-restart wrapper")
                logger.info("Attempting to restart Gradio interface...")
                
                # Try to restart just the Gradio interface
                try:
                    if 'demo' in globals() and hasattr(demo, 'close'):
                        demo.close()
                    # The main() function should handle restarting
                except:
                    pass
                
                # If all else fails, exit and let systemd or user restart
                logger.error("Please restart manually or use: docsray web --auto-restart")
                logging.shutdown()
                time.sleep(0.1)
                os._exit(42)
                
        except Exception as e:
            logger.error(f"Error during recovery: {e}")
            logging.shutdown()
            time.sleep(0.1)
            os._exit(42)
    
    @staticmethod
    def cleanup_temp_files():
        """Clean up old temporary files"""
        try:
            current_time = time.time()
            cleaned = 0
            
            for session_dir in TEMP_DIR.iterdir():
                if session_dir.is_dir():
                    dir_age = current_time - session_dir.stat().st_mtime
                    if dir_age > SESSION_TIMEOUT:
                        shutil.rmtree(session_dir, ignore_errors=True)
                        cleaned += 1
            
            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} old sessions")
                
        except Exception as e:
            logger.error(f"Error cleaning temp files: {e}")

# Memory monitoring thread
def memory_monitor():
    """Background thread to monitor memory usage"""
    while True:
        try:
            ErrorRecoveryMixin.check_memory()
            # Watchdog: restart if no UI activity for HEALTH_TIMEOUT seconds
            if time.time() - LAST_ACTIVITY > HEALTH_TIMEOUT:
                logger.error("Health watchdog timeout, triggering recovery.")
                ErrorRecoveryMixin.trigger_recovery("health_timeout")
            time.sleep(30)  # Check every 30 seconds
        except Exception as e:
            logger.error(f"Memory monitor error: {e}")
            time.sleep(60)

# Start memory monitor
monitor_thread = threading.Thread(target=memory_monitor, daemon=True)
monitor_thread.start()

# [Previous CSS code remains the same]
CUSTOM_CSS = """
/* Global font settings - 한글 가독성을 위한 폰트 설정 */
.gradio-container {
    max-width: 1400px !important;
    font-family: 'Pretendard', 'Noto Sans KR', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif !important;
}

/* Increase base font size */
.gr-text-input, .gr-box, .gr-button, .gr-dropdown {
    font-size: 16px !important;
}

/* Textbox improvements */
.gr-textbox textarea {
    font-size: 16px !important;
    line-height: 1.8 !important;
    color: #2c3e50 !important;
    font-family: 'Pretendard', 'Noto Sans KR', -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', sans-serif !important;
    letter-spacing: -0.02em !important;
}

/* Label improvements */
label, .gr-input-label, .gr-checkbox label {
    font-size: 16px !important;
    font-weight: 600 !important;
    color: #34495e !important;
    margin-bottom: 8px !important;
}

/* Button improvements */
.gr-button {
    font-size: 16px !important;
    font-weight: 600 !important;
    padding: 12px 24px !important;
    border-radius: 8px !important;
    transition: all 0.3s ease !important;
}

.gr-button-primary {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
}

.gr-button-primary:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 5px 15px rgba(0,0,0,0.2) !important;
}

/* Headers */
h1, h2, h3 {
    color: #2c3e50 !important;
    font-weight: 700 !important;
}

h1 { font-size: 32px !important; }
h2 { font-size: 24px !important; }
h3 { font-size: 20px !important; }

/* Markdown improvements */
.markdown-text {
    font-size: 16px !important;
    line-height: 1.6 !important;
    color: #34495e !important;
}

/* Status textbox */
#status-box textarea {
    background-color: #f8f9fa !important;
    border: 2px solid #e9ecef !important;
    border-radius: 8px !important;
    padding: 16px !important;
    font-family: 'D2Coding', 'Consolas', 'Monaco', 'Courier New', monospace !important;
    font-size: 14px !important;
}

/* Answer output styling */
#answer-output textarea, #reference-output textarea {
    background-color: #ffffff !important;
    border: 2px solid #e3e6f0 !important;
    border-radius: 8px !important;
    padding: 20px !important;
    line-height: 1.9 !important;
    font-size: 16px !important;
    color: #2c3e50 !important;
    font-family: 'Pretendard', 'Noto Sans KR', 'Spoqa Han Sans Neo', sans-serif !important;
    letter-spacing: -0.02em !important;
}

/* Dropdown styling */
#doc-dropdown {
    background-color: #f8f9fa !important;
    border: 2px solid #dee2e6 !important;
    border-radius: 8px !important;
    font-size: 16px !important;
}

/* Tab improvements */
.gr-tab-item {
    font-size: 16px !important;
    font-weight: 600 !important;
    padding: 12px 24px !important;
}

/* Accordion improvements */
.gr-accordion {
    border: 2px solid #e9ecef !important;
    border-radius: 8px !important;
    margin: 16px 0 !important;
}

.gr-accordion-header {
    font-size: 16px !important;
    font-weight: 600 !important;
    padding: 16px !important;
    background-color: #f8f9fa !important;
}

/* Example box styling */
.gr-examples {
    background-color: #f8f9fa !important;
    border-radius: 8px !important;
    padding: 16px !important;
    margin-top: 20px !important;
}

.gr-sample-textbox {
    font-size: 15px !important;
    padding: 10px !important;
    border-radius: 6px !important;
    background-color: #ffffff !important;
    border: 1px solid #dee2e6 !important;
    margin: 4px !important;
    cursor: pointer !important;
    transition: all 0.2s ease !important;
}

.gr-sample-textbox:hover {
    background-color: #e9ecef !important;
    transform: translateY(-1px) !important;
}

/* File upload area */
.gr-file {
    border: 3px dashed #dee2e6 !important;
    border-radius: 12px !important;
    padding: 24px !important;
    background-color: #f8f9fa !important;
    font-size: 16px !important;
}

.gr-file:hover {
    border-color: #667eea !important;
    background-color: #f1f3f5 !important;
}

/* Checkbox styling */
.gr-checkbox {
    margin: 12px 0 !important;
}

.gr-checkbox input[type="checkbox"] {
    width: 20px !important;
    height: 20px !important;
    margin-right: 8px !important;
}

/* Progress bar styling */
.gr-progress-bar {
    height: 8px !important;
    border-radius: 4px !important;
    background-color: #e9ecef !important;
}

.gr-progress-bar > div {
    background: linear-gradient(90deg, #667eea 0%, #764ba2 100%) !important;
    border-radius: 4px !important;
}

/* Info text */
.gr-info {
    font-size: 14px !important;
    color: #6c757d !important;
    font-style: italic !important;
}

/* Row and column spacing */
.gr-row {
    gap: 20px !important;
}

.gr-column {
    padding: 16px !important;
}

/* Box shadows for depth */
.gr-box {
    box-shadow: 0 2px 8px rgba(0,0,0,0.08) !important;
    border-radius: 8px !important;
    padding: 20px !important;
}

/* Responsive improvements */
@media (max-width: 768px) {
    .gr-button {
        font-size: 14px !important;
        padding: 10px 16px !important;
    }
    
    .gr-textbox textarea, .gr-text-input {
        font-size: 14px !important;
    }
}
"""

def create_session_dir() -> Path:
    """Create a unique session directory"""
    session_id = str(uuid.uuid4())
    session_dir = TEMP_DIR / session_id
    session_dir.mkdir(exist_ok=True)
    return session_dir

def process_document_with_timeout(file_path: str, session_dir: Path, analyze_visuals: bool = True, progress_callback=None) -> Tuple[list, list, str]:
    """Process a document file with optional timeout handling"""
    
    # If timeout is disabled (0 or negative), run without timeout
    if PDF_PROCESS_TIMEOUT <= 0:
        return _do_process_document(file_path, session_dir, analyze_visuals, progress_callback)
    
    # Otherwise, run with timeout
    start_time = time.time()
    file_name = Path(file_path).name
    
    # Progress: Starting
    safe_progress(progress_callback, 0.1, f"📄 Starting to process: {file_name}")
    
    # Create a thread pool for timeout handling
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        # Submit the processing task
        future = executor.submit(_do_process_document, file_path, session_dir, analyze_visuals, progress_callback)
        
        try:
            # Wait for completion with timeout
            return future.result(timeout=PDF_PROCESS_TIMEOUT)
        except concurrent.futures.TimeoutError:
            # Cancel the future if possible
            future.cancel()
            
            elapsed_time = time.time() - start_time
            error_msg = (
                f"⏰ Processing timeout: {file_name}\n"
                f"⚠️ Document processing exceeded {PDF_PROCESS_TIMEOUT//60} minutes limit\n"
                f"📊 Elapsed time: {elapsed_time:.1f} seconds\n"
                f"💡 Try with a smaller document or disable visual analysis"
            )

            safe_progress(progress_callback, 1.0, error_msg)

            logger.error(f"PDF processing timeout for {file_name} after {elapsed_time:.1f}s")
            gc.collect()
            ErrorRecoveryMixin.trigger_recovery("timeout")
            raise ProcessingTimeoutError(error_msg)
        


def _do_process_document(file_path: str, session_dir: Path, analyze_visuals: bool = True, progress_callback=None) -> Tuple[list, list, str]:
    """Actual document processing function (runs in thread with timeout)"""
    start_time = time.time()
    file_name = Path(file_path).name
    
    try:
        # Extract content with visual analysis option
        extract_kwargs = {
                    "analyze_visuals": analyze_visuals
                }
        if progress_callback is not None:
            status_msg = f"📖 Extracting content from {file_name}..."
            if analyze_visuals:
                status_msg += " (with visual analysis)"
                # Only apply page_limit if it's greater than 0
                if PAGE_LIMIT > 0:
                    extract_kwargs["page_limit"] = PAGE_LIMIT
                    status_msg += f"\n📄 Processing first {PAGE_LIMIT} pages"
                else:
                    status_msg += "\n📄 Processing all pages"
            safe_progress(progress_callback, 0.2, status_msg)

        extracted = pdf_extractor.extract_content(file_path, **extract_kwargs)

        # Create chunks
        if progress_callback is not None:
            progress_msg = "✂️ Creating text chunks..."
            # Show elapsed time
            elapsed = time.time() - start_time
            if elapsed > 10:  # Show elapsed time after 10 seconds
                progress_msg += f" ({elapsed:.0f}s elapsed)"
            safe_progress(progress_callback, 0.4, progress_msg)

        chunks = chunker.process_extracted_file(extracted)

        # Build search index
        if progress_callback is not None:
            progress_msg = "🔍 Building search index..."
            elapsed = time.time() - start_time
            if elapsed > 10:
                progress_msg += f" ({elapsed:.0f}s elapsed)"
            safe_progress(progress_callback, 0.6, progress_msg)

        chunk_index = build_index.build_chunk_index(chunks)

        # Build section representations
        if progress_callback is not None:
            progress_msg = "📊 Building section representations..."
            elapsed = time.time() - start_time
            if elapsed > 10:
                progress_msg += f" ({elapsed:.0f}s elapsed)"
            safe_progress(progress_callback, 0.8, progress_msg)

        sections = section_rep_builder.build_section_reps(extracted["sections"], chunk_index)

        # Save to session cache
        if progress_callback is not None:
            safe_progress(progress_callback, 0.9, "💾 Saving to cache...")

        cache_data = {
            "sections": sections,
            "chunk_index": chunk_index,
            "filename": file_name,
            "metadata": extracted.get("metadata", {})
        }

        # Save with pickle for better performance
        cache_file = session_dir / f"{Path(file_path).stem}_cache.pkl"
        with open(cache_file, "wb") as f:
            pickle.dump(cache_data, f)

        # Calculate processing time
        elapsed_time = time.time() - start_time

        # Create status message
        was_converted = extracted.get("metadata", {}).get("was_converted", False)
        original_format = extracted.get("metadata", {}).get("original_format", "")

        msg = f"✅ Successfully processed: {file_name}\n"
        if was_converted:
            msg += f"🔄 Converted from {original_format.upper()} to PDF\n"
        msg += f"📑 Sections: {len(sections)}\n"
        msg += f"🔍 Chunks: {len(chunks)}\n"
        msg += f"⏱️ Processing time: {elapsed_time:.1f} seconds"

        # Add info about what limits were applied
        if PAGE_LIMIT > 0:
            msg += f"\n📄 Processed first {PAGE_LIMIT} pages"

        if progress_callback is not None:
            safe_progress(progress_callback, 1.0, "✅ Processing complete!")

        return sections, chunk_index, msg
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.error(f"Error processing {file_name} after {elapsed_time:.1f}s: {str(e)}")
        raise


# Remove the wrapper function and use direct call
def process_document(file_path: str, session_dir: Path, analyze_visuals: bool = True, progress_callback=None) -> Tuple[list, list, str]:
    """Process a document file with error recovery and timeout"""
    return process_document_with_timeout(file_path, session_dir, analyze_visuals, progress_callback)

def load_document(file, analyze_visuals: bool, session_state: Dict, progress=gr.Progress()) -> Tuple[Dict, str, gr.update]:
    """Load and process uploaded document with error recovery"""
    if file is None:
        return session_state, "Please upload a document", gr.update()
    
    # Initialize session if needed
    if "session_dir" not in session_state:
        session_state["session_dir"] = str(create_session_dir())
        session_state["documents"] = {}
    
    session_dir = Path(session_state["session_dir"])
    
    # Copy file to session directory
    file_name = Path(file.name).name
    dest_path = session_dir / file_name
    
    # Build initial progress message with limits info
    initial_message = f"📁 Copying {file_name} to session..."
    
    # Add page limit info if applicable
    if PAGE_LIMIT > 0:
        initial_message += f"\n📄 Page Limit: First {PAGE_LIMIT} pages only"
    
    # Add timeout info if applicable  
    if PDF_PROCESS_TIMEOUT > 0:
        initial_message += f"\n⏰ Timeout: {PDF_PROCESS_TIMEOUT//60} minutes max"
    else:
        initial_message += "\n⏰ No timeout limit"
        
    if analyze_visuals:
        initial_message += "\n👁️ Visual analysis enabled (slower)"
    else:
        initial_message += "\n⚡ Visual analysis disabled (faster)"
    
    safe_progress(progress, 0.05, initial_message)
    shutil.copy(file.name, dest_path)
    
    try:
        # Process document with visual analysis option and timeout
        sections, chunk_index, msg = process_document(
            str(dest_path), 
            session_dir,
            analyze_visuals=analyze_visuals,
            progress_callback=progress
        )
        
        if sections is not None:
            # Store in session
            doc_id = Path(file_name).stem
            session_state["documents"][doc_id] = {
                "filename": file_name,
                "sections": sections,
                "chunk_index": chunk_index,
                "path": str(dest_path)
            }
            session_state["current_doc"] = doc_id
            
            # Update dropdown
            choices = [doc["filename"] for doc in session_state["documents"].values()]
            dropdown_update = gr.update(
                choices=choices, 
                value=file_name, 
                visible=True,
                label=f"Loaded Documents ({len(choices)})"
            )
        else:
            dropdown_update = gr.update()
        
        return session_state, msg, dropdown_update
        
    except Exception as e:
        # Log error
        error_msg = f"Error in load_document: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        
        # Track error
        current_time = time.time()
        error_times.append(current_time)
        
        # Clean old errors
        error_times[:] = [t for t in error_times if current_time - t < ERROR_WINDOW]
        
        # Check if we need to trigger recovery
        if len(error_times) >= ERROR_THRESHOLD:
            logger.critical(f"Error threshold reached ({len(error_times)} errors in {ERROR_WINDOW}s)")
            ErrorRecoveryMixin.trigger_recovery("error_threshold")

        if isinstance(e, ProcessingTimeoutError):
            display_msg = str(e)
            ErrorRecoveryMixin.trigger_recovery("timeout")
        else:
            display_msg = f"❌ Error processing document: {str(e)}"    

        return session_state, display_msg, gr.update()


def ask_question(question: str, session_state: Dict, system_prompt: str, use_coarse: bool, progress=gr.Progress()) -> Tuple[str, str]:
    """Process a question with error recovery"""
    if not question.strip():
        return "Please enter a question", ""
    
    if "current_doc" not in session_state or not session_state.get("documents"):
        return "Please upload a document first", ""
    
    try:
        # Get current document
        current_doc = session_state["documents"][session_state["current_doc"]]
        sections = current_doc["sections"]
        chunk_index = current_doc["chunk_index"]
        
        safe_progress(progress, 0.2, "🤔 Thinking about your question...")
        
        # Create chatbot and get answer
        prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        chatbot = PDFChatBot(sections, chunk_index, system_prompt=prompt)
        
        safe_progress(progress, 0.5, "🔍 Searching relevant sections...")
        
        # Get answer
        answer_output, reference_output = chatbot.answer(
            question, 
            fine_only=not use_coarse
        )
        
        safe_progress(progress, 1.0, "✅ Answer ready!")
        
        return answer_output, reference_output
        
    except Exception as e:
        # Log error
        error_msg = f"Error in ask_question: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        
        # Track error
        current_time = time.time()
        error_times.append(current_time)
        
        # Clean old errors
        error_times[:] = [t for t in error_times if current_time - t < ERROR_WINDOW]
        
        # Check if we need to trigger recovery
        if len(error_times) >= ERROR_THRESHOLD:
            logger.critical(f"Error threshold reached ({len(error_times)} errors in {ERROR_WINDOW}s)")
            ErrorRecoveryMixin.trigger_recovery("error_threshold")
        
        # Return safe default
        return f"❌ Error: {str(e)}", ""
    
def switch_document(selected_file: str, session_state: Dict) -> Tuple[Dict, str]:
    """Switch to a different loaded document"""
    if not selected_file or "documents" not in session_state:
        return session_state, "No document selected"
    
    # Find document by filename
    for doc_id, doc_info in session_state["documents"].items():
        if doc_info["filename"] == selected_file:
            session_state["current_doc"] = doc_id
            
            # Get document info
            sections = doc_info["sections"]
            chunks = doc_info["chunk_index"]
            
            msg = f"📄 Switched to: {selected_file}\n"
            msg += f"📑 Sections: {len(sections)}\n"
            msg += f"🔍 Chunks: {len(chunks)}"
            
            return session_state, msg
    
    return session_state, "Document not found"

def clear_session(session_state: Dict) -> Tuple[Dict, str, gr.update, gr.update, gr.update]:
    """Clear all documents and reset session"""
    # Clean up session directory
    if "session_dir" in session_state:
        session_dir = Path(session_state["session_dir"])
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)
    
    # Reset state
    new_state = {}
    
    return (
        new_state,
        "✅ Session cleared successfully",
        gr.update(choices=[], value=None, visible=False),  # dropdown
        gr.update(value=""),  # answer
        gr.update(value="")   # references
    )

def get_supported_formats() -> str:
    """Get list of supported file formats"""
    converter = FileConverter()
    formats = converter.get_supported_formats()
    
    # Group by category
    categories = {
        "Office Documents": ['.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', 'hwp', 'hwpx'],
        "Text Files": ['.txt'],
        "Images": ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp'],
        "PDF": ['.pdf']
    }
    
    info = ""
    for category, extensions in categories.items():
        supported_exts = [ext for ext in extensions if ext in formats or ext == '.pdf']
        if supported_exts:
            info += f"**{category}:** {', '.join(supported_exts)}\n\n"

    return info

# Create Gradio interface with error handling
try:
    with gr.Blocks(
        title="DocsRay - Universal Document Q&A",
        theme=gr.themes.Soft(
            primary_hue="indigo",
            secondary_hue="purple",
            neutral_hue="slate",
            font=[gr.themes.GoogleFont("Noto Sans KR"), gr.themes.GoogleFont("Inter")]
        ),
        css=CUSTOM_CSS
    ) as demo:
        header_html = """
        <div style="text-align: center; padding: 20px 0;">
            <h1 style="font-size: 32px; font-weight: 700; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin-bottom: 8px;">
                🚀 DocsRay
            </h1>
            <p style="font-size: 18px; color: #6b7280; font-weight: 500;">
                Universal Document Q&A System
            </p>
            <p style="font-size: 14px; color: #9ca3af; max-width: 600px; margin: 8px auto;">
                Upload any document (PDF, Word, Excel, PowerPoint, Images, etc.) and ask questions about it!
                All processing happens in your session - no login required.
            </p></div>"""

        # Create the Markdown component
        gr.Markdown(
            header_html,
            elem_classes=["header-section"]
        )
                
        # Session state
        session_state = gr.State({})
        
        # Main layout
        with gr.Row():
            # Left column - Document management
            with gr.Column(scale=1):
                gr.Markdown("### 📁 Document Management")
                
                # File upload
                file_input = gr.File(
                        label="Upload Document",
                        file_types=[
                            ".pdf", 
                            ".docx", ".doc", 
                            ".hwpx", ".hwp",
                            ".xlsx", ".xls", 
                            ".pptx", ".ppt",
                            ".txt", 
                            ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp",
                        ],
                        type="filepath",
                      )

                # Visual analysis toggle
                with gr.Row():
                    analyze_visuals_checkbox = gr.Checkbox(
                        label="👁️ Analyze Visual Content",
                        value=True,
                        info="Extract and analyze images, charts, and figures (slower processing)",
                    )
                
                upload_btn = gr.Button("📤 Process Document", variant="primary", size="lg")
                
                # Document selector (hidden initially)
                doc_dropdown = gr.Dropdown(
                    label="Loaded Documents",
                    choices=[],
                    visible=False,
                    interactive=True,
                    elem_id="doc-dropdown"
                )
                
                # Status with better styling
                status = gr.Textbox(
                    label="Status", 
                    lines=5, 
                    interactive=False,
                    show_label=True
                )
                
                # Action buttons in a row
                with gr.Row():
                    clear_btn = gr.Button("🗑️ Clear Session", variant="stop", size="sm")
                    refresh_btn = gr.Button("🔄 Refresh", variant="secondary", size="sm")
                
                # Supported formats in accordion
                with gr.Accordion("📋 Supported Formats", open=False):
                    gr.Markdown(get_supported_formats())
            
            # Right column - Q&A interface
            with gr.Column(scale=2):
                gr.Markdown("### 💬 Ask Questions")
                
                # Question input
                question_input = gr.Textbox(
                    label="Your Question",
                    placeholder="What would you like to know about the document?",
                    lines=2,
                    autofocus=True
                )
                
                # Search options in a row
                with gr.Row():
                    use_coarse = gr.Checkbox(
                        label="Use Coarse-to-Fine Search",
                        value=True,
                    )
                    ask_btn = gr.Button("🔍 Ask Question", variant="primary", size="lg")
                
                # Results in tabs
                with gr.Tabs():
                    with gr.TabItem("💡 Answer"):
                        answer_output = gr.Textbox(
                            label="",
                            lines=12,
                            interactive=False
                        )
                    
                    with gr.TabItem("📚 References"):
                        reference_output = gr.Textbox(
                            label="",
                            lines=10,
                            interactive=False
                        )
                
                # System prompt in accordion
                with gr.Accordion("⚙️ Advanced Settings", open=False):
                    prompt_input = gr.Textbox(
                        label="System Prompt",
                        lines=5,
                        value=DEFAULT_SYSTEM_PROMPT,
                        info="Customize how the AI responds"
                    )
        
        # Examples section
        with gr.Row():
            gr.Examples(
                examples=[
                    ["What is the main topic of this document?"],
                    ["Summarize the key findings in bullet points"],
                    ["What data or statistics are mentioned?"],
                    ["What are the conclusions or recommendations?"],
                    ["Explain the methodology used"],
                    ["What charts or figures are in this document?"],
                    ["List all the important dates mentioned"],
                    ["What are the limitations discussed?"],
                ],
                inputs=question_input,
                label="Example Questions"
            )
        
        # Update event handlers
        upload_btn.click(
            load_document,
            inputs=[file_input, analyze_visuals_checkbox, session_state],
            outputs=[session_state, status, doc_dropdown],
            show_progress=True
        ).then(
            lambda: gr.update(value=None),
            outputs=[file_input]
        )

        doc_dropdown.change(
            switch_document,
            inputs=[doc_dropdown, session_state],
            outputs=[session_state, status]
        )
        
        ask_btn.click(
            ask_question,
            inputs=[question_input, session_state, prompt_input, use_coarse],
            outputs=[answer_output, reference_output],
            show_progress=True
        )
        
        question_input.submit(
            ask_question,
            inputs=[question_input, session_state, prompt_input, use_coarse],
            outputs=[answer_output, reference_output],
            show_progress=True
        )
        
        clear_btn.click(
            clear_session,
            inputs=[session_state],
            outputs=[session_state, status, doc_dropdown, answer_output, reference_output]
        )
        
        refresh_btn.click(
            lambda s: (s, "🔄 Refreshed", gr.update()),
            inputs=[session_state],
            outputs=[session_state, status, doc_dropdown]
        )

except Exception as e:
    logger.critical(f"Failed to create Gradio interface: {e}")
    ErrorRecoveryMixin.trigger_recovery("interface_creation_failed")

def cleanup_old_sessions():
    """Clean up old session directories (called periodically)"""
    ErrorRecoveryMixin.cleanup_temp_files()

def main():
    """Entry point for docsray-web command with error recovery"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Launch DocsRay web interface")
    parser.add_argument("--share", action="store_true", help="Create public link")
    parser.add_argument("--port", type=int, default=44665, help="Port number")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address")
    parser.add_argument("--timeout", type=int, default=120, help="PDF processing timeout in seconds")
    parser.add_argument("--pages", type=int, default=5, help="Maximum pages to process during visual analysis") 
    args = parser.parse_args()
    
    # Update global timeout if specified
    global PDF_PROCESS_TIMEOUT
    PDF_PROCESS_TIMEOUT = args.timeout
    global PAGE_LIMIT
    PAGE_LIMIT = args.pages
    # Set wrapper environment variable if running under wrapper
    if '--wrapper' in sys.argv:
        os.environ['DOCSRAY_WRAPPER'] = '1'
    
    # Clean up old sessions before starting
    cleanup_old_sessions()
    
    logger.info(f"🚀 Starting DocsRay Web Interface")
    logger.info(f"📍 Local URL: http://localhost:{args.port}")
    logger.info(f"🌐 Network URL: http://{args.host}:{args.port}")
    logger.info(f"⏰ PDF Processing Timeout: {PDF_PROCESS_TIMEOUT} seconds")
    
    try:
        demo.launch(
            server_name=args.host,
            server_port=args.port,
            share=args.share,
            favicon_path=None,
            show_error=True,
            max_threads=40,  # Limit concurrent threads
        )
    except Exception as e:
        logger.critical(f"Server crashed: {e}")
        os._exit(42)  # Special exit code for restart

if __name__ == "__main__":
    main()
