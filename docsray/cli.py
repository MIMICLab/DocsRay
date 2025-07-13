# docsray/cli.py
#!/usr/bin/env python3
"""DocsRay Command Line Interface with Auto-Restart Support and doc Timeout"""

import argparse
import sys
import os
import time
import signal
import threading
import concurrent.futures
from pathlib import Path
from docsray.post_install import hotfix_check
import requests


class ProcessingTimeoutError(Exception):
    """Exception raised when document processing takes too long"""
    pass

def main():
    parser = argparse.ArgumentParser(
        description="DocsRay - Document Question-Answering System",
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
  
  # Start API server
  docsray api --port 8000
  
  # Configure Claude Desktop
  docsray configure-claude
  
  # Process a document with timeout
  docsray process /path/to/document --timeout 300
  
  # Ask a question
  docsray ask document.pdf "What is the main topic?"
  
  # Run performance test
  docsray perf-test /path/to/document "What is this about?" --port 8000
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Download models command
    download_parser = subparsers.add_parser("download-models", help="Download required models")
    download_parser.add_argument("--check", action="store_true", help="Check model status only")
    download_parser.add_argument("--model-type", choices=["lite", "base", "pro"], default="lite",
                                help="Model type to download: lite(4b), base(12b), pro(27b) (default: lite)")
    download_parser.add_argument("--force", action="store_true", help="Force re-download existing models")
    
    # MCP server command
    mcp_parser = subparsers.add_parser("mcp", help="Start MCP server")
    mcp_parser.add_argument("--port", type=int, help="Port number")
    mcp_parser.add_argument("--auto-restart", action="store_true", 
                           help="Enable auto-restart on errors")
    mcp_parser.add_argument("--max-retries", type=int, default=5,
                           help="Max restart attempts (default: 5)")
    mcp_parser.add_argument("--retry-delay", type=int, default=5,
                           help="Delay between restarts in seconds (default: 5)")
    mcp_parser.add_argument("--model-type", choices=["lite", "base", "pro"], default="lite",
                           help="Model type to use: lite(4b), base(12b), pro(27b) (default: lite)")
    
    # Web interface command
    web_parser = subparsers.add_parser("web", help="Start web interface")
    web_parser.add_argument("--share", action="store_true", help="Create public link")
    web_parser.add_argument("--port", type=int, default=44665, help="Port number")
    web_parser.add_argument("--host", default="0.0.0.0", help="Host address")
    web_parser.add_argument("--timeout", type=int, default=120, 
                           help="Document processing timeout in seconds (default: 120)")
    web_parser.add_argument("--pages", type=int, default=5, 
                           help="Maximum pages to process per document (default: 5)")
    web_parser.add_argument("--auto-restart", action="store_true", 
                           help="Enable auto-restart on errors")
    web_parser.add_argument("--max-retries", type=int, default=5,
                           help="Max restart attempts (default: 5)")
    web_parser.add_argument("--retry-delay", type=int, default=5,
                           help="Delay between restarts in seconds (default: 5)")
    web_parser.add_argument("--model-type", choices=["lite", "base", "pro"], default="lite",
                           help="Model type to use: lite(4b), base(12b), pro(27b) (default: lite)")
    
    # API server command
    api_parser = subparsers.add_parser("api", help="Start API server")
    api_parser.add_argument("--port", type=int, default=8000, help="Port number")
    api_parser.add_argument("--host", default="0.0.0.0", help="Host address")
    api_parser.add_argument("--reload", action="store_true", help="Enable hot reload for development")
    api_parser.add_argument("--timeout", type=int, default=300,
                           help="Document processing timeout in seconds (default: 300)")
    api_parser.add_argument("--model-type", choices=["lite", "base", "pro"], default="lite",
                           help="Model type to use: lite(4b), base(12b), pro(27b) (default: lite)")
    
    # Configure Claude command
    config_parser = subparsers.add_parser("configure-claude", help="Configure Claude Desktop")
    
    # Process Document command
    process_parser = subparsers.add_parser("process", help="Process a document file")
    process_parser.add_argument("file_path", help="Path to document file")
    process_parser.add_argument("--no-visuals", action="store_true", 
                            help="Disable visual content analysis")
    process_parser.add_argument("--timeout", type=int, default=300,
                            help="Processing timeout in seconds (default: 300)")
    process_parser.add_argument("--model-type", choices=["lite", "base", "pro"], default="lite",
                            help="Model type to use: lite(4b), base(12b), pro(27b) (default: lite)")

    # Ask question command
    ask_parser = subparsers.add_parser("ask", help="Ask a question about a document")
    ask_parser.add_argument("file_path", help="Path to document file")
    ask_parser.add_argument("question", help="Question to ask")
    ask_parser.add_argument("--model-type", choices=["lite", "base", "pro"], default="lite",
                         help="Model type to use: lite(4b), base(12b), pro(27b) (default: lite)")
    
    # Performance test command
    perf_parser = subparsers.add_parser("perf-test", help="Run performance test against API")
    perf_parser.add_argument("file_path", help="Path to document file")
    perf_parser.add_argument("question", help="Question to ask")
    perf_parser.add_argument("--port", type=int, default=8000, help="API server port (default: 8000)")
    perf_parser.add_argument("--host", default="localhost", help="API server host (default: localhost)")
    perf_parser.add_argument("--iterations", type=int, default=1, help="Number of test iterations (default: 1)")
    
    args = parser.parse_args()
    
    if args.command == "download-models":
        # Set model type environment variable for download
        os.environ["DOCSRAY_MODEL_TYPE"] = args.model_type
        
        from docsray.download_models import download_models, check_models
        if args.check:
            check_models(model_type=args.model_type)
        else:
            download_models(model_type=args.model_type, force=args.force)
    
    elif args.command == "mcp":
        # Set model type environment variable
        os.environ["DOCSRAY_MODEL_TYPE"] = args.model_type
        
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
        # Set model type environment variable
        os.environ["DOCSRAY_MODEL_TYPE"] = args.model_type
        
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
        # Set model type environment variable
        os.environ["DOCSRAY_MODEL_TYPE"] = args.model_type
        
        from docsray.app import main as api_main
        sys.argv = ["docsray-api", "--host", args.host, "--port", str(args.port)]
        if args.timeout:
            sys.argv.extend(["--timeout", str(args.timeout)])
        if args.reload:
            sys.argv.append("--reload")
        api_main()
    
    elif args.command == "configure-claude":
        configure_claude_desktop()
    
    elif args.command == "process":
        # Set model type environment variable
        os.environ["DOCSRAY_MODEL_TYPE"] = args.model_type
        
        process_pdf_cli(args.file_path, args.no_visuals, args.timeout)
    
    elif args.command == "ask":
        # Set model type environment variable
        os.environ["DOCSRAY_MODEL_TYPE"] = args.model_type
        
        ask_question_cli(args.question, args.file_path)
    
    elif args.command == "perf-test":
        run_performance_test(args.file_path, args.question, args.host, args.port, args.iterations)
    
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

def process_pdf_with_timeout(file_path: str, analyze_visuals: bool, timeout: int):
    """Process doc with optional timeout handling"""
    def _process():
        from docsray.scripts import pdf_extractor, chunker, build_index, section_rep_builder
        
        # Extract
        print("📖 Extracting content...", file=sys.stderr)
        extracted = pdf_extractor.extract_content(
            file_path,
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
        
        return sections, chunk_index
    
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

def process_pdf_cli(file_path: str, no_visuals: bool = False, timeout: int = 300):
    """Process a doc file from command line with timeout"""
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return
    
    print(f"📄 Processing: {file_path}", file=sys.stderr)
    
    # Visual analysis 
    analyze_visuals = not no_visuals 
    if no_visuals:
        print("👁️ Visual analysis disabled by user", file=sys.stderr)
    else:
        print("👁️ Visual analysis enabled", file=sys.stderr)
    
    start_time = time.time()
    
    try:
        # Process with timeout
        sections, chunk_index = process_pdf_with_timeout(file_path, analyze_visuals, timeout)
        
        elapsed_time = time.time() - start_time
        print(f"✅ Processing complete!", file=sys.stderr)
        print(f"   Sections: {len(sections)}", file=sys.stderr)
        print(f"   Chunks: {len(chunk_index)}", file=sys.stderr)
        print(f"   Time: {elapsed_time:.1f} seconds", file=sys.stderr)
        
        # Save cache (optional)
        try:
            save_cache(file_path, sections, chunk_index)
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

def save_cache(file_path: str, sections, chunks):
    """Save processed data to cache"""
    import json
    import pickle
    from pathlib import Path
    
    # Create cache directory
    cache_dir = Path.home() / ".docsray" / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    
    # Use doc filename without extension as base name
    file_name = Path(file_path).stem
    
    # Save sections as JSON
    sec_path = cache_dir / f"{file_name}_sections.json"
    with open(sec_path, "w") as f:
        json.dump(sections, f, indent=2)
    
    # Save chunk index as pickle
    idx_path = cache_dir / f"{file_name}_index.pkl"
    with open(idx_path, "wb") as f:
        pickle.dump(chunks, f)
    
    print(f"📁 Cache saved to: {cache_dir}", file=sys.stderr)

def ask_question_cli(question: str, file_path: str):
    """Ask a question about a doc from command line"""
    from docsray.chatbot import PDFChatBot
    import json
    
    # Look for cached data
    cache_dir = Path.home() / ".docsray" / "cache"
    file_name_stem = Path(file_path).stem
    sec_path = cache_dir / f"{file_name_stem}_sections.json"
    idx_path = cache_dir / f"{file_name_stem}_index.pkl"

    if not sec_path.exists() or not idx_path.exists():
        print(f"❌ No cached data for {file_path}. Please process the document first:", file=sys.stderr)
        print(f'docsray process "{file_path}"', file=sys.stderr)
        return
    
    # Load data
    print(f"📁 Loading cached data for {file_path}...", file=sys.stderr)
    try:
        with open(sec_path, "r") as f:
            sections = json.load(f)
        
        import pickle
        with open(idx_path, "rb") as f:
            chunk_index = pickle.load(f)
            
    except Exception as e:
        print(f"❌ Failed to load cached data: {e}", file=sys.stderr)
        print(f'💡 Try reprocessing the document: docsray process "{file_path}"', file=sys.stderr)
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

def run_performance_test(file_path: str, question: str, host: str, port: int, iterations: int):
    """Run performance test against the API server"""
    if not os.path.exists(file_path):
        print(f"❌ Document file not found: {file_path}", file=sys.stderr)
        return
    
    # Get absolute path
    doc_path = str(Path(file_path).resolve())
    
    # Check if API is running
    api_url = f"http://{host}:{port}"
    try:
        response = requests.get(f"{api_url}/health", timeout=5)
        if response.status_code != 200:
            raise Exception(f"Health check failed with status {response.status_code}")
        print(f"✅ API server is healthy at {api_url}", file=sys.stderr)
    except Exception as e:
        print(f"❌ Cannot connect to API server at {api_url}", file=sys.stderr)
        print(f"   Error: {e}", file=sys.stderr)
        print(f"💡 Please start the API server first:", file=sys.stderr)
        print(f"   docsray api --port {port}", file=sys.stderr)
        return
    
    # Run performance test
    print(f"\n🏃 Running performance test...", file=sys.stderr)
    print(f"📄 Document: {file_path}", file=sys.stderr)
    print(f"❓ Question: {question}", file=sys.stderr)
    print(f"🔄 Iterations: {iterations}", file=sys.stderr)
    print(f"🌐 API URL: {api_url}/ask", file=sys.stderr)
    
    times = []
    
    for i in range(iterations):
        print(f"\n--- Iteration {i+1}/{iterations} ---", file=sys.stderr)
        start_time = time.time()
        
        try:
            # Send request to API
            payload = {
                "document_path": doc_path,
                "question": question,
                "use_coarse_search": True
            }
            
            response = requests.post(
                f"{api_url}/ask",
                json=payload,
                timeout=300  # 5 minute timeout
            )
            
            if response.status_code != 200:
                print(f"❌ Request failed with status {response.status_code}", file=sys.stderr)
                print(f"   Response: {response.text}", file=sys.stderr)
                continue
            
            elapsed_time = time.time() - start_time
            times.append(elapsed_time)
            
            # Parse response
            result = response.json()
            
            print(f"⏱️  Time: {elapsed_time:.2f} seconds", file=sys.stderr)
            print(f"\n💡 Answer:", file=sys.stderr)
            print(result["answer"], file=sys.stderr)
            print(f"\n📚 References:", file=sys.stderr)
            print(result["references"], file=sys.stderr)
            
        except requests.exceptions.Timeout:
            print(f"❌ Request timed out after 300 seconds", file=sys.stderr)
        except Exception as e:
            print(f"❌ Error during request: {e}", file=sys.stderr)
    
    # Print summary statistics
    if times:
        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)
        
        print(f"\n📊 Performance Summary:", file=sys.stderr)
        print(f"   Successful requests: {len(times)}/{iterations}", file=sys.stderr)
        print(f"   Average time: {avg_time:.2f} seconds", file=sys.stderr)
        print(f"   Min time: {min_time:.2f} seconds", file=sys.stderr)
        print(f"   Max time: {max_time:.2f} seconds", file=sys.stderr)
        
        if len(times) > 1:
            # First request is usually slower due to cache
            avg_cached = sum(times[1:]) / len(times[1:])
            print(f"   Average (cached): {avg_cached:.2f} seconds", file=sys.stderr)
    else:
        print(f"\n❌ All requests failed", file=sys.stderr)

if __name__ == "__main__":
    main()
