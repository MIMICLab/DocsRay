import asyncio
from docsray.mcp_server import call_tool

async def interactive_test():
    while True:
        print("\n=== MCP Tool Test ===")
        print("1. List Documents")
        print("2. Load a Document")
        print("3. Summarize a Document")
        print("4. Ask a Question")
        print("5. Exit")
        
        choice = input("Choice (1-5): ")
        
        if choice == "1":
            result = await call_tool("list_pdfs", {})
            print(result[0].text)
            
        elif choice == "2":
            filename = input("PDF Filename: ")
            result = await call_tool("load_pdf", {"filename": filename})
            print(result[0].text)
            
        elif choice == "3":
            level = input("Detail Level (brief/standard/detailed): ") or "standard"
            result = await call_tool("summarize_document", {"detail_level": level})
            print(result[0].text)
            
        elif choice == "4":
            question = input("Question: ")
            result = await call_tool("ask_question", {"question": question})
            print(result[0].text)
            
        elif choice == "5":
            break

asyncio.run(interactive_test())