# web_demo.py - Simplified version without login

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


from docsray.chatbot import PDFChatBot, DEFAULT_SYSTEM_PROMPT
from docsray.scripts import pdf_extractor, chunker, build_index, section_rep_builder
from docsray.scripts.file_converter import FileConverter

# Create a temporary directory for this session
TEMP_DIR = Path(tempfile.gettempdir()) / "docsray_web"
TEMP_DIR.mkdir(exist_ok=True)

# Session timeout (24 hours)
SESSION_TIMEOUT = 86400

def create_session_dir() -> Path:
    """Create a unique session directory"""
    session_id = str(uuid.uuid4())
    session_dir = TEMP_DIR / session_id
    session_dir.mkdir(exist_ok=True)
    return session_dir

def process_document(file_path: str, session_dir: Path, analyze_visuals: bool = True, progress_callback=None) -> Tuple[list, list, str]:
    """
    Process a document file and return sections, chunk index, and status message.
    Supports all file formats through auto-conversion.
    
    Args:
        file_path: Path to the document file
        session_dir: Session directory for caching
        progress_callback: Optional progress callback function
    """
    start_time = time.time()
    file_name = Path(file_path).name
    
    # Progress: Starting
    if progress_callback is not None:
        progress_callback(0.1, f"📄 Starting to process: {file_name}")
    
    # Extract content with visual analysis option
    if progress_callback is not None:
        status_msg = f"📖 Extracting content from {file_name}..."
        if analyze_visuals:
            status_msg += " (with visual analysis)"
        progress_callback(0.2, status_msg)
    
    extracted = pdf_extractor.extract_content(
        file_path,
        analyze_visuals=analyze_visuals,
        page_limit=5
    )
    # Create chunks
    if progress_callback is not None:
        progress_callback(0.4, "✂️ Creating text chunks...")
    
    chunks = chunker.process_extracted_file(extracted)
    
    # Build search index
    if progress_callback is not None:
        progress_callback(0.6, "🔍 Building search index...")
    
    chunk_index = build_index.build_chunk_index(chunks)
    
    # Build section representations
    if progress_callback is not None:
        progress_callback(0.8, "📊 Building section representations...")
    
    sections = section_rep_builder.build_section_reps(extracted["sections"], chunk_index)
    
    # Save to session cache
    if progress_callback is not None:
        progress_callback(0.9, "💾 Saving to cache...")
    
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
    
    if progress_callback is not None:
        progress_callback(1.0, "✅ Processing complete!")
    
    return sections, chunk_index, msg

    
def load_document(file, analyze_visuals: bool, session_state: Dict, progress=gr.Progress()) -> Tuple[Dict, str, gr.update]:
    """Load and process uploaded document with progress tracking"""
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
    
    progress(0.05, f"📁 Copying {file_name} to session...")
    shutil.copy(file.name, dest_path)
    
    # Process document with visual analysis option
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

def ask_question(question: str, session_state: Dict, system_prompt: str, use_coarse: bool, progress=gr.Progress()) -> Tuple[str, str]:
    """Process a question about the current document with progress tracking"""
    if not question.strip():
        return "Please enter a question", ""
    
    if "current_doc" not in session_state or not session_state.get("documents"):
        return "Please upload a document first", ""
    
    # Get current document
    current_doc = session_state["documents"][session_state["current_doc"]]
    sections = current_doc["sections"]
    chunk_index = current_doc["chunk_index"]
    
    if progress is not None:
        progress(0.2, "🤔 Thinking about your question...")
    
    # Create chatbot and get answer
    prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
    chatbot = PDFChatBot(sections, chunk_index, system_prompt=prompt)
    
    if progress is not None:
        progress(0.5, "🔍 Searching relevant sections...")
    
    # Get answer
    answer_output, reference_output = chatbot.answer(
        question, 
        fine_only=not use_coarse
    )
    
    if progress is not None:
        progress(1.0, "✅ Answer ready!")
    
    return answer_output, reference_output
        

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
        "Office Documents": ['.docx', '.doc', '.xlsx', '.xls', '.pptx', '.ppt', '.odt', '.ods', '.odp'],
        "Text Files": ['.txt', '.md', '.rst', '.rtf'],
        "Web Files": ['.html', '.htm', '.xml'],
        "Images": ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp'],
        "E-books": ['.epub', '.mobi'],
        "PDF": ['.pdf']
    }
    
    info = "📄 **Supported File Formats:**\n\n"
    for category, extensions in categories.items():
        supported_exts = [ext for ext in extensions if ext in formats or ext == '.pdf']
        if supported_exts:
            info += f"**{category}:** {', '.join(supported_exts)}\n"

    
    return info

# Create Gradio interface
with gr.Blocks(
    title="DocsRay - Universal Document Q&A",
    theme=gr.themes.Soft(),
    css="""
    .gradio-container {
        max-width: 1200px !important;
    }
    #doc-dropdown {
        background-color: #f8f9fa;
    }
    """
) as demo:
    # Header
    gr.Markdown(
        """
        # 🚀 DocsRay - Universal Document Q&A System
        
        Upload any document (PDF, Word, Excel, PowerPoint, Images, etc.) and ask questions about it!
        All processing happens in your session - no login required.

        This demo only processes first 5 pages of each uploaded document.
        """
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
                        ".xlsx", ".xls", 
                        ".pptx", ".ppt",
                        ".txt", ".md", ".rtf", ".rst",
                        ".html", ".htm", ".xml",
                        ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp",
                        ".epub", ".mobi",
                    ],
                    type="filepath",
                  )
            
            # Visual analysis toggle
            with gr.Row():
                analyze_visuals_checkbox = gr.Checkbox(
                    label="👁️ Analyze Visual Content",
                    value=True,
                    info="Extract and analyze images, charts, and figures (slower but more comprehensive)",
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
                    info="Recommended for better accuracy"
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

def cleanup_old_sessions():
    """Clean up old session directories (called periodically)"""
    import time
    current_time = time.time()
    cleaned = 0
    
    for session_dir in TEMP_DIR.iterdir():
        if session_dir.is_dir():
            # Check if directory is older than SESSION_TIMEOUT
            dir_age = current_time - session_dir.stat().st_mtime
            if dir_age > SESSION_TIMEOUT:
                shutil.rmtree(session_dir, ignore_errors=True)
                cleaned += 1
    
    if cleaned > 0:
        print(f"🧹 Cleaned up {cleaned} old sessions")

def main():
    """Entry point for docsray-web command"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Launch DocsRay web interface")
    parser.add_argument("--share", action="store_true", help="Create public link")
    parser.add_argument("--port", type=int, default=44665, help="Port number")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address")
    
    args = parser.parse_args()
    
    # Clean up old sessions before starting
    cleanup_old_sessions()
    
    print(f"🚀 Starting DocsRay Web Interface")
    print(f"📍 Local URL: http://localhost:{args.port}")
    print(f"🌐 Network URL: http://{args.host}:{args.port}")
    
    demo.queue(max_size=10).launch(
        server_name=args.host,
        server_port=args.port,
        share=args.share,
        favicon_path=None,
        show_error=True
    )

if __name__ == "__main__":
    main()