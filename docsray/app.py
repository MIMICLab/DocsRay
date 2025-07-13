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
    version="1.6.0"
)

# Cache for processed documents
document_cache: Dict[str, Dict[str, Any]] = {}
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

# Removed initialize_chatbot function as it's no longer needed

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "DocsRay Universal Document Question-Answering API",
        "version": "1.6.0",
        "status": "ready",
        "cached_documents": len(document_cache),
        "supported_formats": [
            "PDF", "Word (DOCX/DOC)", "Excel (XLSX/XLS)", 
            "PowerPoint (PPTX/PPT)", "HWP/HWPX", "Images (PNG/JPG/etc)", "Text"
        ],
        "endpoints": {
            "POST /ask": "Ask a question about any document",
            "GET /cache/info": "Get information about cached documents",
            "POST /cache/clear": "Clear document cache",
            "GET /health": "Health check",
            "GET /supported-formats": "Get list of supported file formats"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "cached_documents_count": len(document_cache),
        "cache_size_mb": sum(len(str(v)) for v in document_cache.values()) / (1024 * 1024)
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

@app.get("/cache/info")
async def get_cache_info():
    """Get information about cached documents."""
    cache_info = []
    for path, data in document_cache.items():
        file_ext = Path(data["document_name"]).suffix.lower()
        converter = FileConverter()
        file_type = converter.SUPPORTED_FORMATS.get(file_ext, "PDF" if file_ext == ".pdf" else "Unknown")
        
        cache_info.append({
            "document_path": path,
            "document_name": data["document_name"],
            "document_type": file_type,
            "sections_count": len(data["sections"]),
            "chunks_count": len(data["chunk_index"])
        })
    
    return {
        "cached_documents": cache_info,
        "total_count": len(document_cache)
    }

@app.post("/ask")
async def ask_question(
    document_path: str = Body(...),
    question: str = Body(...),
    use_coarse_search: bool = Body(True)
):
    """
    Ask a question about a document.

    Args:
        document_path: Path to the document file
        question: The user's question
        use_coarse_search: Whether to use coarse-to-fine search (default: True)

    Returns:
        JSON response with answer and references
    """
    if not question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    
    if not os.path.exists(document_path):
        raise HTTPException(status_code=404, detail=f"Document file not found: {document_path}")
    
    try:
        # Check if document is already cached
        doc_path_str = str(Path(document_path).resolve())
        
        if doc_path_str not in document_cache:
            # Process document if not cached
            print(f"📄 Processing new document: {document_path}")
            sections, chunk_index, temp_file = process_document_file(document_path)
            
            # Create chatbot and cache it
            chatbot = PDFChatBot(
                sections=sections,
                chunk_index=chunk_index
            )
            
            document_cache[doc_path_str] = {
                "chatbot": chatbot,
                "sections": sections,
                "chunk_index": chunk_index,
                "document_name": os.path.basename(document_path)
            }
        else:
            print(f"📚 Using cached document: {document_path}")
        
        # Get cached data
        cached_data = document_cache[doc_path_str]
        chatbot = cached_data["chatbot"]
        document_name = cached_data["document_name"]
        
        # Get answer from chatbot
        fine_only = not use_coarse_search
        answer_output, reference_output = chatbot.answer(
            question, 
            fine_only=fine_only
        )
        
        return {
            "document_path": document_path,
            "document_name": document_name,
            "question": question,
            "answer": answer_output,
            "references": reference_output,
            "search_method": "coarse-to-fine" if use_coarse_search else "fine-only"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error processing question: {str(e)}"
        )

@app.post("/cache/clear")
async def clear_cache():
    """
    Clear the document cache.
    """
    global document_cache
    count = len(document_cache)
    document_cache.clear()
    
    return {
        "message": "Cache cleared successfully",
        "documents_cleared": count
    }

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up temporary files on shutdown"""
    cleanup_temp_files()

def main():
    """Entry point for docsray-api command"""
    parser = argparse.ArgumentParser(description="Launch DocsRay API server")
    parser.add_argument("--host", default="0.0.0.0", help="Host address")
    parser.add_argument("--port", type=int, default=8000, help="Port number")
    parser.add_argument("--reload", action="store_true", help="Enable hot reload for development")
    parser.add_argument("--timeout", type=int, default=300, 
                       help="Document processing timeout in seconds (default: 300)") 
    args = parser.parse_args()
    
    print("🚀 Starting DocsRay API server...")
    print("📝 Server accepts document paths with each request")
    print("💾 Documents will be cached after first processing")
    print("🔄 Use --reload for development mode (hot reload enabled)")
    
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