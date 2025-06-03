# src/chatbot.py
import sys
import os
import json
import asyncio
from docsray.search.section_coarse_search import coarse_search_sections
from docsray.search.fine_search import fine_search_chunks
from docsray.inference.embedding_model import embedding_model
from docsray.inference.llm_model import local_llm, local_llm_large
from docsray.config import FAST_MODE, STANDARD_MODE, FULL_FEATURE_MODE

DEFAULT_SYSTEM_PROMPT = (
    "You are a document-grounded assistant.\n"
    "• Use ONLY the information provided in <Document Context> as evidence.\n"
    "• When quoting, silently repair broken lines or spacing caused by chunking, "
    "and merge fragments so the sentence flows naturally.\n"
    "• Paraphrase or summarize rather than copying large passages verbatim.\n\n"
)

class PDFChatBot:
    def __init__(self, sections, chunk_index, system_prompt: str = DEFAULT_SYSTEM_PROMPT):
        """
        Parameters
        ----------
        sections : list[dict]
            Each element contains keys such as ``"title"``, ``"title_emb"``,
            ``"avg_chunk_emb"``, etc.
        chunk_index : list[dict]
            Each chunk is a dictionary like
            ``{"embedding": [...], "metadata": {...}}``.
        system_prompt : str
            System prompt that is prepended before calling the LLM.
        """
        self.sections = sections
        self.chunk_index = chunk_index
        self.system_prompt = system_prompt

    def build_prompt(self, user_query, retrieved_chunks):
        """
        Construct the prompt that will be sent to the LLM.

        Parameters
        ----------
        user_query : str
            The question entered by the user.
        retrieved_chunks : list[dict]
            A list of chunks in the form
            ``[{"embedding": [...], "metadata": {...}}, ...]``.

        Returns
        -------
        str
            A fully formatted prompt string.
        """
        context_parts = []
        for item in retrieved_chunks:
            meta = item.get("metadata", {})
            section_title = meta.get("section_title", "")
            content = meta.get("content", "")
            context_parts.append(f"[{section_title}] {content}")
        context_text = "\n\n".join(context_parts)
        prompt = f"{self.system_prompt}\n\n=== Document Context ===\n{context_text}\n\n=== User Question ===\n{user_query}\n\n=== Answer ===\n"
        return prompt.strip()

        
    def answer(self, query: str, beta: float = 0.5, max_iterations = 2, fine_only=False):
        """
        End‑to‑end answer generation pipeline.

        Steps
        -----
        1. **Coarse Search** – Find the top *top_sections* sections at the section level.  
        2. **Fine Search** – Within those sections, retrieve the top *top_chunks* chunks.  
        3. **LLM Generation** – Send a prompt to the LLM and return the generated answer.

        Parameters
        ----------
        query : str
            User question.
        beta : float, default = 0.5
            Interpolation weight for coarse search scoring.
        top_sections : int, default = 10
            Number of sections to retain in the coarse search.
        top_chunks : int, default = 5
            Number of chunks to use in the fine search.
        streaming : bool, default = False
            If ``True``, stream tokens as they are generated.

        Returns
        -------
        str
            The LLM’s answer text.
        """
        chunk_index = self.chunk_index
        sections = self.sections

        augmented_query = query

        if FAST_MODE:
            top_sections = 3
            top_chunks = 5
        elif STANDARD_MODE:
            top_sections = 5
            top_chunks = 10
        else:
            top_sections = 7
            top_chunks = 15

        for iter in range(max_iterations):
            query_emb = embedding_model.get_embedding(augmented_query, is_query=True)
            # 1st Search
            if fine_only:              
                relevant_secs = self.sections
            else:
                # Coarse Search (section level)
                relevant_secs = coarse_search_sections(query_emb, sections, 
                                                       beta=beta, 
                                                       top_k=top_sections * (max_iterations - iter + 1))        
            # Fine Search (chunk level)
            best_chunks = fine_search_chunks(query_emb, chunk_index, 
                                             relevant_secs, 
                                             top_k=top_chunks * (max_iterations - iter + 1), 
                                             fine_only=fine_only)
            # Build a single string that contains the content of every retrieved chunk
            combined_answer = "\n\n".join(
                chunk["metadata"].get("content", "") for chunk in best_chunks
            )
            # Ask the LLM to improve the user query based on ALL retrieved evidence
            query_improvement_prompt = (
                f"The user question is: {query}\n\n"
                f"The retrieved chunks are:\n{combined_answer}\n\n"
                "Write ONE concise follow‑up question that would help retrieve even more relevant information.\n"
                "Return ONLY the question text. Do not include any additional text or explanations."
            )
            raw_improved_query = local_llm.generate(query_improvement_prompt)
            # clean up
            improved_query = local_llm.strip_response(raw_improved_query)
            augmented_query = query + ':' + improved_query

        query_emb = embedding_model.get_embedding(augmented_query, is_query=True) 
        if fine_only:              
            relevant_secs = self.sections
        else:
            # Coarse Search (section level)
            relevant_secs = coarse_search_sections(query_emb, sections, beta=beta, top_k=top_sections)   
        # Fine Search (chunk level)            
                       
        best_chunks = fine_search_chunks(query_emb, chunk_index, 
                                         relevant_secs, top_k=top_chunks, 
                                         fine_only=fine_only)
        # Generate answer with LLM
        prompt = self.build_prompt(query, best_chunks)
        import time
        start_time = time.time()
        answer_text = local_llm_large.generate(prompt)
        end_time = time.time()
        print(f"LLM generation took {end_time - start_time:.2f} seconds")
        answer = answer_text.split("=== Document Context ===")[1].split("=== User Question ===")
        reference_output = answer[0].strip()
        answer_output = local_llm_large.strip_response(answer[1])
        return answer_output, reference_output

if __name__ == "__main__":
    sections_path = "data/extracted/sections_with_emb.json"
    chunk_index_path = "data/index/sample_chunks_vectors.json"

    if not os.path.exists(sections_path):
        print(f"[ERROR] Sections file not found: {sections_path}")
        exit(1)
    else:
        with open(sections_path, 'r', encoding='utf-8') as f:
            sections = json.load(f)

    if not os.path.exists(chunk_index_path):
        print(f"[ERROR] Chunk index file not found: {chunk_index_path}")
        exit(1)
    else:
        with open(chunk_index_path, 'r', encoding='utf-8') as f:
            chunk_index = json.load(f)

    chatbot = PDFChatBot(sections, chunk_index)
    print("Chatbot is ready. Enter your question below:")

    while True:
        query = input("Question (or type 'exit' to quit): ")
        if query.lower() == "exit":
            break
        answer_output, reference_output = chatbot.answer(query)
        print("Answer Output:", answer_output)
        print("Reference Output:", reference_output)

async def answer_async(self, query: str, **kwargs):
    """비동기 답변 생성 (웹/API용)"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, self.answer, query, **kwargs)