# docsray/app.py

import uvicorn
import json
import os
import argparse
from pathlib import Path
from typing import Optional, Dict, Any
from fastapi import FastAPI, Body, HTTPException
import tempfile
import atexit

from docsray.chatbot import PDFChatBot
from docsray.scripts import pdf_extractor, chunker, build_index, section_rep_builder
from docsray.scripts.file_converter import FileConverter

app = FastAPI(
    title="DocsRay API",
    description="Universal Document Question-Answering System API",
    version="1.5.3"
)

# Global variables to store the current document data
current_chatbot: Optional[PDFChatBot] = None
current_document_name: Optional[str] = None
current_sections: Optional[list] = None
current_chunk_index: Optional[list] = None
temp_files_to_cleanup: set = set()  # Track temporary files

def cleanup_temp_files():
    """Clean up temporary files on exit"""
    for temp_file in temp_files_to_cleanup:
        try:
            if os.path.exists(temp_file):
                os.unlink(temp_file)
                print(f"🗑️  Cleaned up temporary file: {temp_file}")
        except Exception as e:
            print(f"⚠️  Failed to clean up {temp_file}: {e}")
    temp_files_to_cleanup.clear()

# Register cleanup function
atexit.register(cleanup_temp_files)

def process_document_file(document_path: str) -> tuple[list, list, Optional[str]]:
    """
    Process a document file and return sections, chunk index, and temp file path.
    
    Args:
        document_path: Path to the document file
        
    Returns:
        Tuple of (sections, chunk_index, temp_file_path)
        
    Raises:
        FileNotFoundError: If document file doesn't exist
        ValueError: If file format is not supported
        RuntimeError: If processing fails
    """
    if not os.path.exists(document_path):
        raise FileNotFoundError(f"Document file not found: {document_path}")
    
    # Check if file format is supported
    converter = FileConverter()
    if not converter.is_supported(document_path) and not document_path.lower().endswith('.pdf'):
        raise ValueError(f"Unsupported file format: {Path(document_path).suffix}")
    
    temp_file_path = None
    
    try:
        print(f"📄 Processing document: {document_path}")
        
        # Extract content (with automatic conversion if needed)
        print("📖 Extracting content...")
        extracted = pdf_extractor.extract_content(document_path)
        
        # Check if a temporary file was created
        if extracted.get("metadata", {}).get("was_converted", False):
            # For converted files, pdf_extractor might have created a temp file
            # We'll track it for cleanup
            temp_file_path = extracted.get("metadata", {}).get("temp_pdf_path")
            if temp_file_path and os.path.exists(temp_file_path):
                temp_files_to_cleanup.add(temp_file_path)
        
        # Create chunks
        print("✂️  Creating chunks...")
        chunks = chunker.process_extracted_file(extracted)
        
        # Build search index
        print("🔍 Building search index...")
        chunk_index = build_index.build_chunk_index(chunks)
        
        # Build section representations
        print("📊 Building section representations...")
        sections = section_rep_builder.build_section_reps(extracted["sections"], chunk_index)
        
        print(f"✅ Processing complete!")
        print(f"   Sections: {len(sections)}")
        print(f"   Chunks: {len(chunks)}")
        
        return sections, chunk_index, temp_file_path
        
    except Exception as e:
        # Clean up temp file if processing failed
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                temp_files_to_cleanup.discard(temp_file_path)
            except:
                pass
        raise RuntimeError(f"Failed to process document: {str(e)}")

def initialize_chatbot(document_path: str, system_prompt: Optional[str] = None):
    """
    Initialize the chatbot with a document file.
    Supports PDF, DOCX, XLSX, PPTX, HWP, images, and other formats.
    
    Args:
        document_path: Path to the document file
        system_prompt: Optional custom system prompt
    """
    global current_chatbot, current_document_name, current_sections, current_chunk_index
    
    try:
        # Process the document
        sections, chunk_index, temp_file = process_document_file(document_path)
        
        # Store global state
        current_sections = sections
        current_chunk_index = chunk_index
        current_document_name = os.path.basename(document_path)
        
        # Create chatbot
        current_chatbot = PDFChatBot(
            sections=sections, 
            chunk_index=chunk_index, 
            system_prompt=system_prompt
        )
        
        print(f"✅ Chatbot initialized with document: {current_document_name}")
        
    except Exception as e:
        print(f"❌ Failed to initialize chatbot: {e}")
        raise

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "DocsRay Universal Document Question-Answering API",
        "version": "1.5.2",
        "current_document": current_document_name,
        "status": "ready" if current_chatbot else "no_document_loaded",
        "supported_formats": [
            "PDF", "Word (DOCX/DOC)", "Excel (XLSX/XLS)", 
            "PowerPoint (PPTX/PPT)", "HWP/HWPX", "Images (PNG/JPG/etc)", "Text"
        ],
        "endpoints": {
            "POST /ask": "Ask a question about the loaded document",
            "GET /info": "Get information about the current document",
            "POST /reload": "Reload document with new system prompt",
            "GET /health": "Health check",
            "GET /supported-formats": "Get list of supported file formats"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "document_loaded": current_chatbot is not None,
        "current_document": current_document_name
    }

@app.get("/supported-formats")
async def get_supported_formats():
    """Get list of supported file formats."""
    converter = FileConverter()
    formats = converter.get_supported_formats()
    
    return {
        "formats": formats,
        "total": len(formats) + 1  # +1 for PDF
    }

@app.get("/info")
async def get_document_info():
    """Get information about the currently loaded document."""
    if not current_chatbot:
        raise HTTPException(status_code=404, detail="No document loaded")
    
    # Determine file type
    file_ext = Path(current_document_name).suffix.lower()
    converter = FileConverter()
    file_type = converter.SUPPORTED_FORMATS.get(file_ext, "PDF" if file_ext == ".pdf" else "Unknown")
    
    return {
        "document_name": current_document_name,
        "document_type": file_type,
        "sections_count": len(current_sections) if current_sections else 0,
        "chunks_count": len(current_chunk_index) if current_chunk_index else 0,
        "status": "loaded"
    }

@app.post("/ask")
async def ask_question(
    question: str = Body(..., embed=True),
    use_coarse_search: bool = Body(True, embed=True)
):
    """
    Ask a question about the loaded document.

    Args:
        question: The user's question
        use_coarse_search: Whether to use coarse-to-fine search (default: True)

    Returns:
        JSON response with answer and references
    """
    if not current_chatbot:
        raise HTTPException(
            status_code=404, 
            detail="No document loaded. Please start the server with a document file."
        )
    
    if not question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    
    try:
        # Get answer from chatbot
        fine_only = not use_coarse_search
        answer_output, reference_output = current_chatbot.answer(
            question, 
            fine_only=fine_only
        )
        
        return {
            "question": question,
            "answer": answer_output,
            "references": reference_output,
            "document_name": current_document_name,
            "search_method": "coarse-to-fine" if use_coarse_search else "fine-only"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error processing question: {str(e)}"
        )

@app.post("/reload")
async def reload_document(
    system_prompt: Optional[str] = Body(None, embed=True)
):
    """
    Reload the current document with a new system prompt.
    
    Args:
        system_prompt: Optional new system prompt
    """
    if not current_sections or not current_chunk_index:
        raise HTTPException(status_code=404, detail="No document data available to reload")
    
    global current_chatbot
    
    try:
        # Recreate chatbot with new system prompt
        current_chatbot = PDFChatBot(
            sections=current_sections,
            chunk_index=current_chunk_index,
            system_prompt=system_prompt
        )
        
        return {
            "message": "Document reloaded successfully",
            "document_name": current_document_name,
            "system_prompt_updated": system_prompt is not None
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error reloading document: {str(e)}"
        )

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up temporary files on shutdown"""
    cleanup_temp_files()

def main():
    """Entry point for docsray-api command"""
    parser = argparse.ArgumentParser(description="Launch DocsRay API server")
    parser.add_argument("--host", default="0.0.0.0", help="Host address")
    parser.add_argument("--port", type=int, default=8000, help="Port number")
    parser.add_argument("--doc", "--pdf", type=str, help="Path to document file to load")
    parser.add_argument("--system-prompt", type=str, help="Custom system prompt")
    parser.add_argument("--reload", action="store_true", help="Enable hot reload for development")
    parser.add_argument("--timeout", type=int, default=300, 
                       help="Document processing timeout in seconds (default: 300)") 
    args = parser.parse_args()
    
    # Initialize chatbot if document path is provided
    if args.doc:
        doc_path = Path(args.doc).resolve()
        print(f"🚀 Starting DocsRay API server...")
        print(f"📄 Loading document: {doc_path}")
        
        # Check file format
        converter = FileConverter()
        file_ext = doc_path.suffix.lower()
        if converter.is_supported(str(doc_path)) or file_ext == '.pdf':
            file_type = converter.SUPPORTED_FORMATS.get(file_ext, "PDF" if file_ext == ".pdf" else "Unknown")
            print(f"📋 File type: {file_type}")
        else:
            print(f"❌ Unsupported file format: {file_ext}")
            print(f"💡 Supported formats: PDF, {', '.join(converter.SUPPORTED_FORMATS.keys())}")
            return
        
        try:
            initialize_chatbot(str(doc_path), args.system_prompt)
        except Exception as e:
            print(f"❌ Failed to load document: {e}")
            print("💡 Server will start without a loaded document")
    else:
        print("🚀 Starting DocsRay API server without document")
        print("💡 Use the /reload endpoint or restart with --doc argument to load a document")
    
    print(f"🌐 Server will be available at: http://{args.host}:{args.port}")
    print(f"📚 API documentation: http://{args.host}:{args.port}/docs")
    print(f"🔄 Health check: http://{args.host}:{args.port}/health")
    
    # Start the server
    uvicorn.run(
        app, 
        host=args.host, 
        port=args.port,
        reload=args.reload
    )

if __name__ == "__main__":
    main()