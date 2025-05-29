# app.py

import uvicorn
import json
import os
from fastapi import FastAPI, Body

from docsray.chatbot import PDFChatBot

app = FastAPI()

# 1) Load section information (sections_with_emb.json)
sections_path = "data/extracted/sections_with_emb.json"
with open(sections_path, 'r', encoding='utf-8') as f:
    sections_data = json.load(f)

# 2) Load chunk index (sample_chunks_vectors.json)
chunk_index_path = "data/index/sample_chunks_vectors.json"
with open(chunk_index_path, 'r', encoding='utf-8') as f:
    chunk_index_data = json.load(f)

chatbot = PDFChatBot(sections_data, chunk_index_data)

@app.post("/ask")
def ask_question(question: str = Body(..., embed=True)):
    """
    FastAPI endpoint that returns an answer for the given question.

    Parameters
    ----------
    question : str
        The user’s question text, passed in the request body.

    Returns
    -------
    dict
        A JSON dictionary with a single key ``"answer"``.
    """
    answer_output, reference_output = chatbot.answer(question)
    return {"answer": answer_output, "reference": reference_output}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)