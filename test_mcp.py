import asyncio
from docsray.mcp_server import call_tool

async def interactive_test():
    while True:
        print("\n명령을 선택하세요:")
        print("1. PDF 목록 보기")
        print("2. PDF 로드하기")
        print("3. 문서 요약하기")
        print("4. 질문하기")
        print("5. 종료")
        
        choice = input("선택: ")
        
        if choice == "1":
            result = await call_tool("list_pdfs", {})
            print(result[0].text)
            
        elif choice == "2":
            filename = input("PDF 파일명: ")
            result = await call_tool("load_pdf", {"filename": filename})
            print(result[0].text)
            
        elif choice == "3":
            level = input("상세도 (brief/standard/detailed): ") or "standard"
            result = await call_tool("summarize_document", {"detail_level": level})
            print(result[0].text)
            
        elif choice == "4":
            question = input("질문: ")
            result = await call_tool("ask_question", {"question": question})
            print(result[0].text)
            
        elif choice == "5":
            break

asyncio.run(interactive_test())