import asyncio
from docsray.mcp_server import call_tool
import json

async def print_result(result):
    """Pretty print the result"""
    if result and len(result) > 0:
        print("\n" + "="*80)
        print(result[0].text)
        print("="*80)

async def basic_operations():
    """Basic document operations menu"""
    while True:
        print("\n=== Basic Operations ===")
        print("1. Get Current Directory")
        print("2. Set Current Directory")
        print("3. List Documents")
        print("4. Load a Document")
        print("5. Ask a Question")
        print("6. Summarize Current Document")
        print("7. Visual Analysis Settings")
        print("0. Back to Main Menu")
        
        choice = input("\nChoice: ")
        
        if choice == "1":
            result = await call_tool("get_current_directory", {})
            await print_result(result)
            
        elif choice == "2":
            path = input("New directory path: ")
            result = await call_tool("set_current_directory", {"folder_path": path})
            await print_result(result)
            
        elif choice == "3":
            result = await call_tool("list_documents", {})
            await print_result(result)
            
        elif choice == "4":
            filename = input("Document filename: ")
            analyze = input("Analyze visuals? (y/n): ").lower() == 'y'
            result = await call_tool("load_document", {
                "filename": filename,
                "analyze_visuals": analyze
            })
            await print_result(result)
            
        elif choice == "5":
            question = input("Your question: ")
            coarse = input("Use coarse search? (y/n, default y): ").lower() != 'n'
            result = await call_tool("ask_question", {
                "question": question,
                "use_coarse_search": coarse
            })
            await print_result(result)
            
        elif choice == "6":
            level = input("Detail level (brief/standard/detailed, default standard): ") or "standard"
            result = await call_tool("summarize_document", {"detail_level": level})
            await print_result(result)
            
        elif choice == "7":
            print("\n1. Get Status")
            print("2. Enable Visual Analysis")
            print("3. Disable Visual Analysis")
            sub_choice = input("Choice: ")
            
            if sub_choice == "1":
                result = await call_tool("get_visual_analysis_status", {})
                await print_result(result)
            elif sub_choice == "2":
                result = await call_tool("set_visual_analysis", {"enabled": True})
                await print_result(result)
            elif sub_choice == "3":
                result = await call_tool("set_visual_analysis", {"enabled": False})
                await print_result(result)
                
        elif choice == "0":
            break

async def batch_operations():
    """Batch processing operations menu"""
    while True:
        print("\n=== Batch Operations ===")
        print("1. Process All Documents")
        print("2. Search by Content")
        print("3. Load Document by Search")
        print("4. Get All Summaries")
        print("0. Back to Main Menu")
        
        choice = input("\nChoice: ")
        
        if choice == "1":
            print("\nProcess All Documents Options:")
            folder = input("Folder path (Enter for current): ") or None
            analyze = input("Analyze visuals? (y/n): ").lower() == 'y'
            summaries = input("Generate summaries? (y/n, default y): ").lower() != 'n'
            level = input("Summary level (brief/standard/detailed, default brief): ") or "brief"
            max_files = input("Max files to process (Enter for all): ")
            
            params = {
                "analyze_visuals": analyze,
                "generate_summaries": summaries,
                "detail_level": level
            }
            if folder:
                params["folder_path"] = folder
            if max_files:
                params["max_files"] = int(max_files)
                
            result = await call_tool("process_all_documents", params)
            await print_result(result)
            
        elif choice == "2":
            query = input("Search query: ")
            level = input("Detail level (brief/standard/detailed, default brief): ") or "brief"
            top_k = input("Number of results (default 5): ") or "5"
            
            result = await call_tool("search_by_content", {
                "query": query,
                "detail_level": level,
                "top_k": int(top_k)
            })
            await print_result(result)
            
        elif choice == "3":
            query = input("Search query to load best match: ")
            result = await call_tool("load_document_by_summary_search", {"query": query})
            await print_result(result)
            
        elif choice == "4":
            level = input("Filter by detail level (brief/standard/detailed, Enter for all): ") or None
            params = {}
            if level:
                params["detail_level"] = level
                
            result = await call_tool("get_document_summaries", params)
            await print_result(result)
            
        elif choice == "0":
            break

async def search_operations():
    """File system search operations menu"""
    while True:
        print("\n=== File System Search ===")
        print("1. Get Recommended Search Paths")
        print("2. Analyze a Path")
        print("3. Search for Documents")
        print("4. Get Cached Search Results")
        print("0. Back to Main Menu")
        
        choice = input("\nChoice: ")
        
        if choice == "1":
            result = await call_tool("get_recommended_search_paths", {})
            await print_result(result)
            
        elif choice == "2":
            path = input("Path to analyze: ")
            result = await call_tool("analyze_search_path", {"path": path})
            await print_result(result)
            
        elif choice == "3":
            print("\nSearch Options:")
            start_path = input("Start path (Enter for home): ") or None
            extensions = input("Extensions (comma-separated, e.g., pdf,docx): ")
            search_term = input("Search term in filename: ") or None
            max_results = input("Max results (default 1000): ") or "1000"
            
            params = {"max_results": int(max_results)}
            if start_path:
                params["start_path"] = start_path
            if extensions:
                params["extensions"] = [e.strip() for e in extensions.split(",")]
            if search_term:
                params["search_term"] = search_term
                
            result = await call_tool("search_documents", params)
            await print_result(result)
            
        elif choice == "4":
            cache_key = input("Cache key: ")
            result = await call_tool("get_search_results", {"cache_key": cache_key})
            await print_result(result)
            
        elif choice == "0":
            break

async def cache_operations():
    """Cache management operations menu"""
    while True:
        print("\n=== Cache Management ===")
        print("1. Get Cache Info")
        print("2. Clear All Cache")
        print("0. Back to Main Menu")
        
        choice = input("\nChoice: ")
        
        if choice == "1":
            result = await call_tool("get_cache_info", {})
            await print_result(result)
            
        elif choice == "2":
            confirm = input("Are you sure you want to clear all cache? (yes/no): ")
            if confirm.lower() == "yes":
                result = await call_tool("clear_all_cache", {})
                await print_result(result)
            else:
                print("Cache clearing cancelled.")
                
        elif choice == "0":
            break

async def quick_test():
    """Quick test sequence"""
    print("\n=== Running Quick Test Sequence ===")
    
    # 1. Get current directory
    print("\n1. Getting current directory...")
    result = await call_tool("get_current_directory", {})
    await print_result(result)
    
    # 2. List documents
    print("\n2. Listing documents...")
    result = await call_tool("list_documents", {})
    await print_result(result)
    
    # 3. Get cache info
    print("\n3. Getting cache info...")
    result = await call_tool("get_cache_info", {})
    await print_result(result)
    
    # 4. Get visual analysis status
    print("\n4. Getting visual analysis status...")
    result = await call_tool("get_visual_analysis_status", {})
    await print_result(result)
    
    print("\n✅ Quick test completed!")

async def interactive_test():
    """Main menu"""
    print("\n🚀 DocsRay MCP Test Tool")
    print("=" * 50)
    
    while True:
        print("\n=== Main Menu ===")
        print("1. Basic Operations")
        print("2. Batch Processing")
        print("3. File System Search")
        print("4. Cache Management")
        print("5. Quick Test (Run basic checks)")
        print("0. Exit")
        
        choice = input("\nChoice: ")
        
        if choice == "1":
            await basic_operations()
        elif choice == "2":
            await batch_operations()
        elif choice == "3":
            await search_operations()
        elif choice == "4":
            await cache_operations()
        elif choice == "5":
            await quick_test()
        elif choice == "0":
            print("\n👋 Goodbye!")
            break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    asyncio.run(interactive_test())