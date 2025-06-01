# web_demo.py - Simplified version without login

import os
import shutil
from typing import Tuple, List, Optional, Dict
import tempfile
from pathlib import Path
import json
import uuid

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

def process_document(file_path: str, session_dir: Path) -> Tuple[list, list, str]:
    """
    Process a document file and return sections, chunk index, and status message.
    Supports all file formats through auto-conversion.
    """
    try:
        print(f"📄 Processing document: {file_path}")
        
        # Extract content (auto-converts if needed)
        extracted = pdf_extractor.extract_content(file_path)
        
        # Create chunks
        print("✂️  Creating chunks...")
        chunks = chunker.process_extracted_file(extracted)
        
        # Build search index
        print("🔍 Building search index...")
        chunk_index = build_index.build_chunk_index(chunks)
        
        # Build section representations
        print("📊 Building section representations...")
        sections = section_rep_builder.build_section_reps(extracted["sections"], chunk_index)
        
        # Save to session cache
        cache_data = {
            "sections": sections,
            "chunk_index": chunk_index,
            "filename": Path(file_path).name,
            "metadata": extracted.get("metadata", {})
        }
        
        cache_file = session_dir / f"{Path(file_path).stem}_cache.json"
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False)
        
        # Create status message
        was_converted = extracted.get("metadata", {}).get("was_converted", False)
        original_format = extracted.get("metadata", {}).get("original_format", "")
        
        msg = f"✅ Successfully processed: {Path(file_path).name}\n"
        if was_converted:
            msg += f"🔄 Converted from {original_format.upper()} to PDF\n"
        msg += f"📑 Sections: {len(sections)}\n"
        msg += f"🔍 Chunks: {len(chunks)}"
        
        return sections, chunk_index, msg
        
    except Exception as e:
        return None, None, f"❌ Error processing document: {str(e)}"

def load_document(file, session_state: Dict) -> Tuple[Dict, str, gr.Update]:
    """Load and process uploaded document"""
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
    shutil.copy(file.name, dest_path)
    
    # Process document
    sections, chunk_index, msg = process_document(str(dest_path), session_dir)
    
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
        dropdown_update = gr.update(choices=choices, value=file_name, visible=True)
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
            return session_state, f"Switched to: {selected_file}"
    
    return session_state, "Document not found"

def ask_question(question: str, session_state: Dict, system_prompt: str, use_coarse: bool) -> Tuple[str, str]:
    """Process a question about the current document"""
    if not question.strip():
        return "Please enter a question", ""
    
    if "current_doc" not in session_state or not session_state.get("documents"):
        return "Please upload a document first", ""
    
    # Get current document
    current_doc = session_state["documents"][session_state["current_doc"]]
    sections = current_doc["sections"]
    chunk_index = current_doc["chunk_index"]
    
    # Create chatbot and get answer
    prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
    chatbot = PDFChatBot(sections, chunk_index, system_prompt=prompt)
    
    answer_output, reference_output = chatbot.answer(
        question, 
        fine_only=not use_coarse
    )
    
    return answer_output, reference_output

def clear_session(session_state: Dict) -> Tuple[Dict, str, gr.Update, gr.Update, gr.Update]:
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
        "Session cleared",
        gr.update(value="", visible=False),  # dropdown
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
with gr.Blocks(title="DocsRay - Universal Document Q&A") as demo:
    # Header
    gr.Markdown(
        """
        # 🚀 DocsRay - Universal Document Q&A System
        
        Upload any document (PDF, Word, Excel, PowerPoint, Images, etc.) and ask questions about it!
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
                file_types=[".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", 
                           ".txt", ".md", ".html", ".png", ".jpg", ".jpeg"],
                type="filepath"
            )
            upload_btn = gr.Button("📤 Process Document", variant="primary")
            
            # Document selector (hidden initially)
            doc_dropdown = gr.Dropdown(
                label="Loaded Documents",
                choices=[],
                visible=False,
                interactive=True
            )
            
            # Status
            status = gr.Textbox(label="Status", lines=4, interactive=False)
            
            # Clear button
            clear_btn = gr.Button("🗑️ Clear All Documents", variant="stop")
            
            # Supported formats
            with gr.Accordion("Supported Formats", open=False):
                gr.Markdown(get_supported_formats())
        
        # Right column - Q&A interface
        with gr.Column(scale=2):
            gr.Markdown("### 💬 Ask Questions")
            
            # System prompt
            with gr.Accordion("System Prompt", open=False):
                prompt_input = gr.Textbox(
                    label="Customize the system prompt",
                    lines=5,
                    value=DEFAULT_SYSTEM_PROMPT
                )
            
            # Question input
            question_input = gr.Textbox(
                label="Your Question",
                placeholder="What would you like to know about the document?",
                lines=2
            )
            
            # Search options
            with gr.Row():
                use_coarse = gr.Checkbox(
                    label="Use Coarse-to-Fine Search",
                    value=True,
                    info="Enable section-based search for better accuracy"
                )
                ask_btn = gr.Button("🔍 Ask Question", variant="primary")
            
            # Results
            answer_output = gr.Textbox(
                label="Answer",
                lines=10,
                interactive=False
            )
            
            reference_output = gr.Textbox(
                label="References",
                lines=6,
                interactive=False
            )
    
    # Examples
    gr.Examples(
        examples=[
            ["What is the main topic of this document?"],
            ["Summarize the key findings"],
            ["What data or statistics are mentioned?"],
            ["What are the conclusions or recommendations?"],
            ["Explain the methodology used"],
        ],
        inputs=question_input
    )
    
    # Event handlers
    upload_btn.click(
        load_document,
        inputs=[file_input, session_state],
        outputs=[session_state, status, doc_dropdown]
    )
    
    doc_dropdown.change(
        switch_document,
        inputs=[doc_dropdown, session_state],
        outputs=[session_state, status]
    )
    
    ask_btn.click(
        ask_question,
        inputs=[question_input, session_state, prompt_input, use_coarse],
        outputs=[answer_output, reference_output]
    )
    
    question_input.submit(
        ask_question,
        inputs=[question_input, session_state, prompt_input, use_coarse],
        outputs=[answer_output, reference_output]
    )
    
    clear_btn.click(
        clear_session,
        inputs=[session_state],
        outputs=[session_state, status, doc_dropdown, answer_output, reference_output]
    )

def cleanup_old_sessions():
    """Clean up old session directories (called periodically)"""
    import time
    current_time = time.time()
    
    for session_dir in TEMP_DIR.iterdir():
        if session_dir.is_dir():
            # Check if directory is older than SESSION_TIMEOUT
            dir_age = current_time - session_dir.stat().st_mtime
            if dir_age > SESSION_TIMEOUT:
                shutil.rmtree(session_dir, ignore_errors=True)

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
    
    demo.launch(
        server_name=args.host,
        server_port=args.port,
        share=args.share,
        favicon_path=None
    )

if __name__ == "__main__":
    main()