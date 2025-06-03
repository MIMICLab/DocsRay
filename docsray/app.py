# docsray/app.py

import uvicorn
import json
import os
import argparse
from pathlib import Path
from typing import Optional, Dict, Any
from fastapi import FastAPI, Body, HTTPException

from docsray.chatbot import PDFChatBot
from docsray.scripts import pdf_extractor, chunker, build_index, section_rep_builder

app = FastAPI(
    title="DocsRay API",
    description="PDF Question-Answering System API",
    version="1.3.3"
)

# Global variables to store the current PDF data
current_chatbot: Optional[PDFChatBot] = None
current_pdf_name: Optional[str] = None
current_sections: Optional[list] = None
current_chunk_index: Optional[list] = None

def process_pdf_file(pdf_path: str) -> tuple[list, list]:
    """
    Process a PDF file and return sections and chunk index.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Tuple of (sections, chunk_index)
        
    Raises:
        FileNotFoundError: If PDF file doesn't exist
        RuntimeError: If processing fails
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")
    
    try:
        print(f"📄 Processing PDF: {pdf_path}")
        
        # Extract content from PDF
        print("📖 Extracting content...")
        extracted = pdf_extractor.extract_pdf_content(pdf_path)
        
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
        
        return sections, chunk_index
        
    except Exception as e:
        raise RuntimeError(f"Failed to process PDF: {str(e)}")

def initialize_chatbot(pdf_path: str, system_prompt: Optional[str] = None):
    """
    Initialize the chatbot with a PDF file.
    
    Args:
        pdf_path: Path to the PDF file
        system_prompt: Optional custom system prompt
    """
    global current_chatbot, current_pdf_name, current_sections, current_chunk_index
    
    try:
        # Process the PDF
        sections, chunk_index = process_pdf_file(pdf_path)
        
        # Store global state
        current_sections = sections
        current_chunk_index = chunk_index
        current_pdf_name = os.path.basename(pdf_path)
        
        # Create chatbot
        current_chatbot = PDFChatBot(
            sections=sections, 
            chunk_index=chunk_index, 
            system_prompt=system_prompt
        )
        
        print(f"✅ Chatbot initialized with PDF: {current_pdf_name}")
        
    except Exception as e:
        print(f"❌ Failed to initialize chatbot: {e}")
        raise

@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "message": "DocsRay PDF Question-Answering API",
        "version": "0.1.0",
        "current_pdf": current_pdf_name,
        "status": "ready" if current_chatbot else "no_pdf_loaded",
        "endpoints": {
            "POST /ask": "Ask a question about the loaded PDF",
            "GET /info": "Get information about the current PDF",
            "POST /reload": "Reload PDF with new system prompt",
            "GET /health": "Health check"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "pdf_loaded": current_chatbot is not None,
        "current_pdf": current_pdf_name
    }

@app.get("/info")
async def get_pdf_info():
    """Get information about the currently loaded PDF."""
    if not current_chatbot:
        raise HTTPException(status_code=404, detail="No PDF loaded")
    
    return {
        "pdf_name": current_pdf_name,
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
    Ask a question about the loaded PDF.

    Args:
        question: The user's question
        use_coarse_search: Whether to use coarse-to-fine search (default: True)

    Returns:
        JSON response with answer and references
    """
    if not current_chatbot:
        raise HTTPException(
            status_code=404, 
            detail="No PDF loaded. Please start the server with a PDF file."
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
            "pdf_name": current_pdf_name,
            "search_method": "coarse-to-fine" if use_coarse_search else "fine-only"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Error processing question: {str(e)}"
        )

@app.post("/reload")
async def reload_pdf(
    system_prompt: Optional[str] = Body(None, embed=True)
):
    """
    Reload the current PDF with a new system prompt.
    
    Args:
        system_prompt: Optional new system prompt
    """
    if not current_sections or not current_chunk_index:
        raise HTTPException(status_code=404, detail="No PDF data available to reload")
    
    global current_chatbot
    
    try:
        # Recreate chatbot with new system prompt
        current_chatbot = PDFChatBot(
            sections=current_sections,
            chunk_index=current_chunk_index,
            system_prompt=system_prompt
        )
        
        return {
            "message": "PDF reloaded successfully",
            "pdf_name": current_pdf_name,
            "system_prompt_updated": system_prompt is not None
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error reloading PDF: {str(e)}"
        )

def main():
    """Entry point for docsray-api command"""
    parser = argparse.ArgumentParser(description="Launch DocsRay API server")
    parser.add_argument("--host", default="0.0.0.0", help="Host address")
    parser.add_argument("--port", type=int, default=8000, help="Port number")
    parser.add_argument("--pdf", type=str, help="Path to PDF file to load")
    parser.add_argument("--system-prompt", type=str, help="Custom system prompt")
    parser.add_argument("--reload", action="store_true", help="Enable hot reload for development")
    
    args = parser.parse_args()
    
    # Initialize chatbot if PDF path is provided
    if args.pdf:
        pdf_path = Path(args.pdf).resolve()
        print(f"🚀 Starting DocsRay API server...")
        print(f"📄 Loading PDF: {pdf_path}")
        
        try:
            initialize_chatbot(str(pdf_path), args.system_prompt)
        except Exception as e:
            print(f"❌ Failed to load PDF: {e}")
            print("💡 Server will start without a loaded PDF")
    else:
        print("🚀 Starting DocsRay API server without PDF")
        print("💡 Use the /reload endpoint or restart with --pdf argument to load a PDF")
    
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