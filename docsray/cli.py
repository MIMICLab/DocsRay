# docsray/cli.py
#!/usr/bin/env python3
"""DocsRay Command Line Interface with Auto-Restart Support and PDF Timeout"""

import argparse
import sys
import os
import time
import signal
import threading
import concurrent.futures
from pathlib import Path
from docsray.config import FAST_MODE
from docsray.post_install import hotfix_check


class ProcessingTimeoutError(Exception):
    """Exception raised when document processing takes too long"""
    pass

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
  
  # Start MCP server with auto-restart
  docsray mcp --auto-restart
  
  # Start web interface
  docsray web
  
  # Start web interface with auto-restart
  docsray web --auto-restart
  
  # Start web interface with custom timeout
  docsray web --timeout 600
  
  # Start API server with PDF
  docsray api --pdf /path/to/document.pdf --port 8000
  
  # Configure Claude Desktop
  docsray configure-claude
  
  # Process a PDF with timeout
  docsray process /path/to/document.pdf --timeout 300
  
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
    mcp_parser.add_argument("--auto-restart", action="store_true", 
                           help="Enable auto-restart on errors")
    mcp_parser.add_argument("--max-retries", type=int, default=5,
                           help="Max restart attempts (default: 5)")
    mcp_parser.add_argument("--retry-delay", type=int, default=5,
                           help="Delay between restarts in seconds (default: 5)")
    
    # Web interface command
    web_parser = subparsers.add_parser("web", help="Start web interface")
    web_parser.add_argument("--share", action="store_true", help="Create public link")
    web_parser.add_argument("--port", type=int, default=44665, help="Port number")
    web_parser.add_argument("--host", default="0.0.0.0", help="Host address")
    web_parser.add_argument("--timeout", type=int, default=120, 
                           help="PDF processing timeout in seconds (default: 120)")
    web_parser.add_argument("--pages", type=int, default=5, 
                           help="Maximum pages to process per PDF (default: 5)")
    web_parser.add_argument("--auto-restart", action="store_true", 
                           help="Enable auto-restart on errors")
    web_parser.add_argument("--max-retries", type=int, default=5,
                           help="Max restart attempts (default: 5)")
    web_parser.add_argument("--retry-delay", type=int, default=5,
                           help="Delay between restarts in seconds (default: 5)")
    
    # API server command
    api_parser = subparsers.add_parser("api", help="Start API server")
    api_parser.add_argument("--port", type=int, default=8000, help="Port number")
    api_parser.add_argument("--host", default="0.0.0.0", help="Host address")
    api_parser.add_argument("--pdf", type=str, help="Path to PDF file to load")
    api_parser.add_argument("--system-prompt", type=str, help="Custom system prompt")
    api_parser.add_argument("--reload", action="store_true", help="Enable hot reload for development")
    api_parser.add_argument("--timeout", type=int, default=300,
                           help="PDF processing timeout in seconds (default: 300)")
    
    # Configure Claude command
    config_parser = subparsers.add_parser("configure-claude", help="Configure Claude Desktop")
    
    # Process PDF command
    process_parser = subparsers.add_parser("process", help="Process a PDF file")
    process_parser.add_argument("pdf_path", help="Path to PDF file")
    process_parser.add_argument("--no-visuals", action="store_true", 
                            help="Disable visual content analysis")
    process_parser.add_argument("--timeout", type=int, default=300,
                            help="Processing timeout in seconds (default: 300)")

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
        if args.auto_restart:
            # Use auto-restart wrapper
            from docsray.auto_restart import SimpleServiceMonitor
            
            cmd = [sys.executable, "-m", "docsray.mcp_server"]
            os.environ["DOCSRAY_AUTO_RESTART"] = "1"  # Tell child processes we're under auto‑restart
            monitor = SimpleServiceMonitor(
                service_name="DocsRay MCP",
                command_args=cmd,
                max_retries=args.max_retries,
                retry_delay=args.retry_delay
            )
            
            try:
                monitor.run()
            except KeyboardInterrupt:
                print("\n🛑 MCP Server stopped by user", file=sys.stderr)
        else:
            # Direct start
            import asyncio
            from docsray.mcp_server import main as mcp_main
            asyncio.run(mcp_main())
    
    elif args.command == "web":
        if args.auto_restart:
            # Use auto-restart wrapper
            from docsray.auto_restart import SimpleServiceMonitor
            
            # Build command for web service
            cmd = [sys.executable, "-m", "docsray.web_demo"]
            os.environ["DOCSRAY_AUTO_RESTART"] = "1"
            if args.port != 44665:
                cmd.extend(["--port", str(args.port)])
            if args.host != "0.0.0.0":
                cmd.extend(["--host", args.host])
            if args.share:
                cmd.append("--share")
            if args.timeout != 120:
                cmd.extend(["--timeout", str(args.timeout)])
            if args.pages != 5:
                cmd.extend(["--pages", str(args.pages)])
                
            monitor = SimpleServiceMonitor(
                service_name="DocsRay Web",
                command_args=cmd,
                max_retries=args.max_retries,
                retry_delay=args.retry_delay
            )
            
            print("🚀 Starting DocsRay Web Interface with auto-restart enabled", file=sys.stderr)
            print(f"♻️  Max retries: {args.max_retries}", file=sys.stderr)
            print(f"⏱️  Retry delay: {args.retry_delay} seconds", file=sys.stderr)
            
            try:
                monitor.run()
            except KeyboardInterrupt:
                print("\n🛑 Web Interface stopped by user", file=sys.stderr)
        else:
            # Direct start without auto-restart
            from docsray.web_demo import main as web_main
            sys.argv = ["docsray-web"]
            if args.share:
                sys.argv.append("--share")
            if args.port:
                sys.argv.extend(["--port", str(args.port)])
            if args.host:
                sys.argv.extend(["--host", args.host])
            if args.timeout:
                sys.argv.extend(["--timeout", str(args.timeout)])
            if args.pages:
                sys.argv.extend(["--pages", str(args.pages)])
            web_main()

    
    elif args.command == "api":
        from docsray.app import main as api_main
        sys.argv = ["docsray-api", "--host", args.host, "--port", str(args.port)]
        if args.pdf:
            sys.argv.extend(["--pdf", args.pdf])
        if args.system_prompt:
            sys.argv.extend(["--system-prompt", args.system_prompt])
        if args.timeout:
            sys.argv.extend(["--timeout", str(args.timeout)])
        if args.reload:
            sys.argv.append("--reload")
        api_main()
    
    elif args.command == "configure-claude":
        configure_claude_desktop()
    
    elif args.command == "process":
        process_pdf_cli(args.pdf_path, args.no_visuals, args.timeout)
    
    elif args.command == "ask":
        ask_question_cli(args.question, args.pdf)
    
    else:
        if hotfix_check():
            parser.print_help()
        else:
            return

def configure_claude_desktop():
    """Configure Claude Desktop for MCP integration"""
    import json
    import platform
    import sys
    import os
    from pathlib import Path
    
    # Determine config path based on OS
    system = platform.system()
    if system == "Darwin":  # macOS
        config_path = Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif system == "Windows":
        config_path = Path(os.environ["APPDATA"]) / "Claude" / "claude_desktop_config.json"
    else:
        print("❌ Unsupported OS for Claude Desktop", file=sys.stderr)
        return
    
    # Get DocsRay installation path
    try:
        import docsray
        
        if hasattr(docsray, '__file__') and docsray.__file__ is not None:
            docsray_path = Path(docsray.__file__).parent
        else:
            if hasattr(docsray, '__path__'):
                docsray_path = Path(docsray.__path__[0])
            else:
                raise AttributeError("Cannot find docsray module path")
                
    except (AttributeError, ImportError, IndexError) as e:
        print(f"⚠️  Warning: Could not find docsray module path: {e}", file=sys.stderr)
        
        if 'docsray' in sys.modules:
            module = sys.modules['docsray']
            if hasattr(module, '__file__') and module.__file__:
                docsray_path = Path(module.__file__).parent
            else:
                current_file = Path(__file__).resolve()
                docsray_path = current_file.parent
        else:
            cwd = Path.cwd()
            if (cwd / "docsray").exists():
                docsray_path = cwd / "docsray"
            else:
                docsray_path = cwd
    
    mcp_server_path = docsray_path / "mcp_server.py"

    if not mcp_server_path.exists():
        print(f"❌ MCP server not found at: {mcp_server_path}", file=sys.stderr)
        
        possible_locations = [
            docsray_path.parent / "docsray" / "mcp_server.py",
            Path(__file__).parent / "mcp_server.py",
            Path.cwd() / "docsray" / "mcp_server.py",
            Path.cwd() / "mcp_server.py",
        ]
        
        for location in possible_locations:
            if location.exists():
                mcp_server_path = location
                docsray_path = location.parent
                print(f"✅ Found MCP server at: {mcp_server_path}", file=sys.stderr)
                break
        else:
            print("❌ Could not locate mcp_server.py", file=sys.stderr)
            print("💡 Please ensure DocsRay is properly installed", file=sys.stderr)
            print("   Try: pip install -e . (in the DocsRay directory)", file=sys.stderr)
            return
    
    # Create config
    config = {
        "mcpServers": {
            "docsray": {
                "command": sys.executable,
                "args": [str(mcp_server_path)],
                "cwd": str(docsray_path.parent),
                "timeout": 1800000,  # ms
                "env": {
                    "PYTHONUNBUFFERED": "1",
                    "MCP_TIMEOUT": "1800"  # sec
                },
                "stdio": {
                    "readTimeout": 1800000,  # ms
                    "writeTimeout": 1800000
                }
            }
        }
    }
    # Ensure directory exists
    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"❌ Failed to create config directory: {e}", file=sys.stderr)
        return
    
    # Check if config already exists and merge
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                existing = json.load(f)
            
            if "mcpServers" in existing:
                existing["mcpServers"]["docsray"] = config["mcpServers"]["docsray"]
                config = existing
        except json.JSONDecodeError:
            print("⚠️  Warning: Existing config file is invalid, overwriting...", file=sys.stderr)
        except Exception as e:
            print(f"⚠️  Warning: Could not read existing config: {e}", file=sys.stderr)
    
    # Write config
    try:
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
        
        print(f"✅ Claude Desktop configured successfully!", file=sys.stderr)
        print(f"📁 Config location: {config_path}", file=sys.stderr)
        print(f"🐍 Python: {sys.executable}", file=sys.stderr)
        print(f"📄 MCP Server: {mcp_server_path}", file=sys.stderr)
        print(f"📂 Working directory: {docsray_path.parent}", file=sys.stderr)
        print("\n⚠️  Please restart Claude Desktop for changes to take effect.", file=sys.stderr)
        
    except Exception as e:
        print(f"❌ Failed to write config file: {e}", file=sys.stderr)
        print(f"📁 Attempted path: {config_path}", file=sys.stderr)
        print("\n💡 You can manually create the config file with:", file=sys.stderr)
        print(json.dumps(config, indent=2), file=sys.stderr)

def process_pdf_with_timeout(pdf_path: str, analyze_visuals: bool, timeout: int):
    """Process PDF with optional timeout handling"""
    def _process():
        from docsray.scripts import pdf_extractor, chunker, build_index, section_rep_builder
        
        # Extract
        print("📖 Extracting content...", file=sys.stderr)
        extracted = pdf_extractor.extract_content(
            pdf_path,
            analyze_visuals=analyze_visuals
        )

        # Chunk
        print("✂️  Creating chunks...", file=sys.stderr)
        chunks = chunker.process_extracted_file(extracted)
        
        # Build index
        print("🔍 Building search index...", file=sys.stderr)
        chunk_index = build_index.build_chunk_index(chunks)
        
        # Build section representations
        print("📊 Building section representations...", file=sys.stderr)
        sections = section_rep_builder.build_section_reps(extracted["sections"], chunk_index)
        
        return sections, chunks
    
    # Check if timeout is enabled
    if timeout > 0:
        # Run with timeout
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            print(f"⏰ Processing timeout: {timeout} seconds ({timeout//60}m {timeout%60}s)", file=sys.stderr)
            future = executor.submit(_process)
            
            try:
                sections, chunks = future.result(timeout=timeout)
                return sections, chunks
            except concurrent.futures.TimeoutError:
                future.cancel()
                print(f"\n⏰ Processing timeout exceeded!", file=sys.stderr)
                print(f"❌ Document processing took longer than {timeout} seconds", file=sys.stderr)
                print(f"💡 Try with a smaller document or use --no-visuals flag", file=sys.stderr)
                raise ProcessingTimeoutError(f"Processing timeout after {timeout} seconds")
    else:
        # Run without timeout
        print("⏰ No timeout limit set", file=sys.stderr)
        return _process()

def process_pdf_cli(pdf_path: str, no_visuals: bool = False, timeout: int = 300):
    """Process a PDF file from command line with timeout"""
    if not os.path.exists(pdf_path):
        print(f"❌ File not found: {pdf_path}")
        return
    
    print(f"📄 Processing: {pdf_path}", file=sys.stderr)
    
    # Visual analysis 
    analyze_visuals = not no_visuals 
    if no_visuals:
        print("👁️ Visual analysis disabled by user", file=sys.stderr)
    else:
        print("👁️ Visual analysis enabled", file=sys.stderr)
    
    start_time = time.time()
    
    try:
        # Process with timeout
        sections, chunks = process_pdf_with_timeout(pdf_path, analyze_visuals, timeout)
        
        elapsed_time = time.time() - start_time
        print(f"✅ Processing complete!", file=sys.stderr)
        print(f"   Sections: {len(sections)}", file=sys.stderr)
        print(f"   Chunks: {len(chunks)}", file=sys.stderr)
        print(f"   Time: {elapsed_time:.1f} seconds", file=sys.stderr)
        
        # Save cache (optional)
        try:
            save_cache(pdf_path, sections, chunks)
            print(f"💾 Cache saved for future use", file=sys.stderr)
        except Exception as e:
            print(f"⚠️  Warning: Could not save cache: {e}", file=sys.stderr)
            
    except ProcessingTimeoutError as e:
        print(f"\n❌ {e}", file=sys.stderr)
        return
    except KeyboardInterrupt:
        print(f"\n🛑 Processing interrupted by user", file=sys.stderr)
        return
    except Exception as e:
        elapsed_time = time.time() - start_time
        print(f"\n❌ Processing failed after {elapsed_time:.1f} seconds", file=sys.stderr)
        print(f"Error: {e}", file=sys.stderr)
        return

def save_cache(pdf_path: str, sections, chunks):
    """Save processed data to cache"""
    import json
    import pickle
    from pathlib import Path
    
    # Create cache directory
    cache_dir = Path.home() / ".docsray" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Use PDF filename without extension as base name
    pdf_name = Path(pdf_path).stem
    
    # Save sections as JSON
    sec_path = cache_dir / f"{pdf_name}_sections.json"
    with open(sec_path, "w") as f:
        json.dump(sections, f, indent=2)
    
    # Save chunk index as pickle
    idx_path = cache_dir / f"{pdf_name}_index.pkl"
    with open(idx_path, "wb") as f:
        pickle.dump(chunks, f)
    
    print(f"📁 Cache saved to: {cache_dir}", file=sys.stderr)

def ask_question_cli(question: str, pdf_name: str):
    """Ask a question about a PDF from command line"""
    from docsray.chatbot import PDFChatBot
    import json
    
    # Look for cached data
    cache_dir = Path.home() / ".docsray" / "cache"
    sec_path = cache_dir / f"{pdf_name}_sections.json"
    idx_path = cache_dir / f"{pdf_name}_index.pkl"
    
    if not sec_path.exists() or not idx_path.exists():
        print(f"❌ No cached data for {pdf_name}. Please process the PDF first:", file=sys.stderr)
        print(f"   docsray process {pdf_name}.pdf", file=sys.stderr)
        return
    
    # Load data
    print(f"📁 Loading cached data for {pdf_name}...", file=sys.stderr)
    try:
        with open(sec_path, "r") as f:
            sections = json.load(f)
        
        import pickle
        with open(idx_path, "rb") as f:
            chunk_index = pickle.load(f)
            
    except Exception as e:
        print(f"❌ Failed to load cached data: {e}", file=sys.stderr)
        print(f"💡 Try reprocessing the PDF: docsray process {pdf_name}.pdf", file=sys.stderr)
        return
    
    # Create chatbot and get answer
    print(f"🤔 Thinking about: {question}", file=sys.stderr)
    start_time = time.time()
    
    try:
        chatbot = PDFChatBot(sections, chunk_index)
        answer, references = chatbot.answer(question)
        
        elapsed_time = time.time() - start_time
        print(f"\n💡 Answer (took {elapsed_time:.1f}s):", file=sys.stderr)
        print(f"{answer}", file=sys.stderr)
        print(f"\n📚 References:", file=sys.stderr)
        print(f"{references}", file=sys.stderr)
        
    except Exception as e:
        print(f"❌ Failed to get answer: {e}", file=sys.stderr)
        return

if __name__ == "__main__":
    main()
