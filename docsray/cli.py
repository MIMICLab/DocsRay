# docsray/cli.py
#!/usr/bin/env python3
"""DocsRay Command Line Interface"""

import argparse
import sys
import os
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(
        description="DocsRay - PDF Question-Answering System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download required models
  docsray download-models
  
  # Start MCP server
  docsray mcp
  
  # Start web interface
  docsray web
  
  # Start API server with PDF
  docsray api --pdf /path/to/document.pdf --port 8000
  
  # Configure Claude Desktop
  docsray configure-claude
  
  # Process a PDF
  docsray process /path/to/document.pdf
  
  # Ask a question
  docsray ask "What is the main topic?" --pdf document.pdf
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Download models command
    download_parser = subparsers.add_parser("download-models", help="Download required models")
    download_parser.add_argument("--check", action="store_true", help="Check model status only")
    
    # MCP server command
    mcp_parser = subparsers.add_parser("mcp", help="Start MCP server")
    mcp_parser.add_argument("--port", type=int, help="Port number")
    
    # Web interface command
    web_parser = subparsers.add_parser("web", help="Start web interface")
    web_parser.add_argument("--share", action="store_true", help="Create public link")
    web_parser.add_argument("--port", type=int, default=44665, help="Port number")
    
    # API server command - 개선된 부분
    api_parser = subparsers.add_parser("api", help="Start API server")
    api_parser.add_argument("--port", type=int, default=8000, help="Port number")
    api_parser.add_argument("--host", default="0.0.0.0", help="Host address")
    api_parser.add_argument("--pdf", type=str, help="Path to PDF file to load")
    api_parser.add_argument("--system-prompt", type=str, help="Custom system prompt")
    api_parser.add_argument("--reload", action="store_true", help="Enable hot reload for development")
    
    # Configure Claude command
    config_parser = subparsers.add_parser("configure-claude", help="Configure Claude Desktop")
    
    # Process PDF command
    process_parser = subparsers.add_parser("process", help="Process a PDF file")
    process_parser.add_argument("pdf_path", help="Path to PDF file")
    
    # Ask question command
    ask_parser = subparsers.add_parser("ask", help="Ask a question about a PDF")
    ask_parser.add_argument("question", help="Question to ask")
    ask_parser.add_argument("--pdf", required=True, help="PDF file name")
    
    args = parser.parse_args()
    
    if args.command == "download-models":
        from docsray.download_models import download_models, check_models
        if args.check:
            check_models()
        else:
            download_models()
    
    elif args.command == "mcp":
        import asyncio
        from docsray.mcp_server import main as mcp_main
        asyncio.run(mcp_main())
    
    elif args.command == "web":
        from docsray.web_demo import main as web_main
        # web_main 함수에 인자 전달
        sys.argv = ["docsray-web"]
        if args.share:
            sys.argv.append("--share")
        if args.port:
            sys.argv.extend(["--port", str(args.port)])
        web_main()
    
    elif args.command == "api":
        from docsray.app import main as api_main
        # api_main 함수에 인자 전달
        sys.argv = ["docsray-api", "--host", args.host, "--port", str(args.port)]
        if args.pdf:
            sys.argv.extend(["--pdf", args.pdf])
        if args.system_prompt:
            sys.argv.extend(["--system-prompt", args.system_prompt])
        if args.reload:
            sys.argv.append("--reload")
        api_main()
    
    elif args.command == "configure-claude":
        configure_claude_desktop()
    
    elif args.command == "process":
        process_pdf_cli(args.pdf_path)
    
    elif args.command == "ask":
        ask_question_cli(args.question, args.pdf)
    
    else:
        parser.print_help()

def configure_claude_desktop():
    """Configure Claude Desktop for MCP integration"""
    import json
    import platform
    
    # Determine config path based on OS
    system = platform.system()
    if system == "Darwin":  # macOS
        config_path = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif system == "Windows":
        config_path = Path(os.environ["APPDATA"]) / "Claude" / "claude_desktop_config.json"
    else:
        print("❌ Unsupported OS for Claude Desktop")
        return
    
    # Get DocsRay installation path
    import docsray
    docsray_path = Path(docsray.__file__).parent
    mcp_server_path = docsray_path / "mcp_server.py"
    
    # Create config
    config = {
        "mcpServers": {
            "docsray": {
                "command": sys.executable,  # Current Python interpreter
                "args": [str(mcp_server_path)],
                "cwd": str(docsray_path.parent),
                "timeout": 1800000,  #  30 minutes
            }
        }
    }
    
    # Ensure directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Check if config already exists
    if config_path.exists():
        with open(config_path, "r") as f:
            existing = json.load(f)
        
        if "mcpServers" in existing:
            existing["mcpServers"]["docsray"] = config["mcpServers"]["docsray"]
            config = existing
    
    # Write config
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    
    print(f"✅ Claude Desktop configured successfully!")
    print(f"📁 Config location: {config_path}")
    print(f"🐍 Python: {sys.executable}")
    print(f"📄 MCP Server: {mcp_server_path}")
    print("\n⚠️  Please restart Claude Desktop for changes to take effect.")

def process_pdf_cli(pdf_path: str):
    """Process a PDF file from command line"""
    from docsray.scripts import pdf_extractor, chunker, build_index, section_rep_builder
    
    if not os.path.exists(pdf_path):
        print(f"❌ File not found: {pdf_path}")
        return
    
    print(f"📄 Processing: {pdf_path}")
    
    # Extract
    print("📖 Extracting content...")
    extracted = pdf_extractor.extract_pdf_content(pdf_path)
    
    # Chunk
    print("✂️  Creating chunks...")
    chunks = chunker.process_extracted_file(extracted)
    
    # Build index
    print("🔍 Building search index...")
    chunk_index = build_index.build_chunk_index(chunks)
    
    # Build section representations
    print("📊 Building section representations...")
    sections = section_rep_builder.build_section_reps(extracted["sections"], chunk_index)
    
    print(f"✅ Processing complete!")
    print(f"   Sections: {len(sections)}")
    print(f"   Chunks: {len(chunks)}")

def ask_question_cli(question: str, pdf_name: str):
    """Ask a question about a PDF from command line"""
    from docsray.chatbot import PDFChatBot
    import json
    
    # Look for cached data
    cache_dir = Path.home() / ".docsray" / "cache"
    sec_path = cache_dir / f"{pdf_name}_sections.json"
    idx_path = cache_dir / f"{pdf_name}_index.pkl"
    
    if not sec_path.exists() or not idx_path.exists():
        print(f"❌ No cached data for {pdf_name}. Please process the PDF first.")
        return
    
    # Load data
    with open(sec_path, "r") as f:
        sections = json.load(f)
    
    import pickle
    with open(idx_path, "rb") as f:
        chunk_index = pickle.load(f)
    
    # Create chatbot and get answer
    print(f"🤔 Thinking...")
    chatbot = PDFChatBot(sections, chunk_index)
    answer, references = chatbot.answer(question)
    
    print(f"\n💡 Answer:\n{answer}")
    print(f"\n📚 References:\n{references}")

if __name__ == "__main__":
    main()