# src/inference/llm_model.py - 환경변수 기반 수정 버전

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from llama_cpp import Llama
import os
import sys
from pathlib import Path

class LlamaTokenizer:
    def __init__(self, llama_model):
        self._llama = llama_model

    def __call__(self, text, add_bos=True, return_tensors=None):
        ids = self._llama.tokenize(text, add_bos=add_bos)
        if return_tensors == "pt":
            return torch.tensor([ids])
        return ids

    def decode(self, ids):
        return self._llama.detokenize(ids).decode("utf-8", errors="ignore")

class LocalLLM:
    def __init__(self, model_name="google/gemma-3-1b-it", device="gpu"):
        self.device = device
        # Convert relative path to absolute path
        if not os.path.isabs(model_name):
            current_dir = Path(__file__).parent.absolute()
            project_root = current_dir.parent.parent  # Go up two levels
            model_name = str(project_root / model_name)
        
        # Check if we're in MCP mode (less verbose)
        is_mcp_mode = os.getenv('DOCSRAY_MCP_MODE') == '1'
        
        if not is_mcp_mode:
            print(f"Loading LLM from: {model_name}", file=sys.stderr)
        
        # Check if file exists
        if not os.path.exists(model_name):
            raise FileNotFoundError(f"Model file not found: {model_name}")
        
        # Create model with less verbose output in MCP mode
        verbose_flag = not is_mcp_mode
        
        self.model = Llama(
                model_path=model_name,
                n_gpu_layers=-1,
                n_ctx=0,
                flash_attn=True,
                no_perf=True,
                logits_all=False,
                verbose=verbose_flag)
        self.tokenizer = LlamaTokenizer(self.model)

    def generate(self, prompt):
        if "gemma" in self.model.model_path.lower():
            prompt = "<start_of_turn>user "+ prompt +"<end_of_turn><start_of_turn>model "
            stop = ['<end_of_turn>']
        else:
            prompt = "<|im_start|>user "+ prompt + "<|im_end|><|im_start|>assistant \n"
            stop = ['<|im_end|>']                
        answer = self.model(prompt,
            max_tokens=0,
            stop=stop,
            echo=True,
            temperature=0.7,
            top_p=0.95,
            repeat_penalty=1.1,
            )
        result = answer['choices'][0]['text']
        return result.strip()


if torch.cuda.is_available():
    device = "cuda"
elif torch.backends.mps.is_available():
    device = "mps"
else:
    device = "cpu"

from docsray import MODEL_DIR
small_model_path = str(MODEL_DIR / "gemma-3-1b-it-GGUF" / "gemma-3-1b-it-Q8_0.gguf")
large_model_path = str(MODEL_DIR / "trillion-7b-preview-GGUF" / "trillion-7b-preview.q8_0.gguf")

# Always load the small model
local_llm = LocalLLM(model_name=small_model_path, device=device)
local_llm_large = LocalLLM(model_name=large_model_path, device=device)