# src/inference/llm_model.py 

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from llama_cpp import Llama
import os
import sys
from pathlib import Path

os.environ['LLAMA_CPP_LOG_LEVEL'] = 'ERROR'

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

# 기존 코드 (line 78-87) 대신:

if torch.cuda.is_available():
    device = "cuda"
elif torch.backends.mps.is_available():
    device = "mps"
else:
    device = "cpu"

# Lazy initialization
local_llm = None
local_llm_large = None

def get_llm_models():
    """Get or create the LLM model instances"""
    global local_llm, local_llm_large
    
    if local_llm is None or local_llm_large is None:
        try:
            from docsray import MODEL_DIR
        except ImportError:
            MODEL_DIR = Path.home() / ".docsray" / "models"
        
        small_model_path = str(MODEL_DIR / "gemma-3-1b-it-GGUF" / "gemma-3-1b-it-Q8_0.gguf")
        large_model_path = str(MODEL_DIR / "trillion-7b-preview-GGUF" / "trillion-7b-preview.q8_0.gguf")
        
        if not os.path.exists(small_model_path) or not os.path.exists(large_model_path):
            raise FileNotFoundError(
                f"Model files not found. Please run 'docsray download-models' first.\n"
                f"Expected locations:\n  {small_model_path}\n  {large_model_path}"
            )
        
        local_llm = LocalLLM(model_name=small_model_path, device=device)
        local_llm_large = LocalLLM(model_name=large_model_path, device=device)
    
    return local_llm, local_llm_large

# For backward compatibility
try:
    local_llm, local_llm_large = get_llm_models()
except:
    pass