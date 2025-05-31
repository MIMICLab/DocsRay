# src/inference/embedding_model.py 

from sentence_transformers import SentenceTransformer
from llama_cpp import Llama
import numpy as np
import torch
import os
import sys
from pathlib import Path

os.environ['LLAMA_CPP_LOG_LEVEL'] = 'ERROR'

EPS = 1e-8              

def _l2_normalize(arr):
    arr = np.asarray(arr, dtype=np.float32)
    norm = np.linalg.norm(arr, axis=-1, keepdims=True) + EPS
    return arr / norm

class EmbeddingModel:
    def __init__(self, model_name_1="BAAI/bge-m3", model_name_2="intfloat/multilingual-e5-large", device="cpu"):
        """
        Load the model and move it to the specified device.
        """
        self.is_gguf = 'gguf' in model_name_1.lower()
        self.device = device
        
        if self.is_gguf:
            # Convert relative path to absolute path
            if not os.path.isabs(model_name_1):
                # Find the project root directory
                current_dir = Path(__file__).parent.absolute()
                project_root = current_dir.parent.parent  # Go up two levels from src/inference/
                model_name_1 = str(project_root / model_name_1)
            
            if not os.path.isabs(model_name_2):
                current_dir = Path(__file__).parent.absolute()
                project_root = current_dir.parent.parent
                model_name_2 = str(project_root / model_name_2)
            
            # Check if we're in MCP mode (less verbose)
            is_mcp_mode = os.getenv('DOCSRAY_MCP_MODE') == '1'
            
            if not is_mcp_mode:
                print(f"Loading model 1 from: {model_name_1}", file=sys.stderr)
                print(f"Loading model 2 from: {model_name_2}", file=sys.stderr)
            
            # Check if files exist
            if not os.path.exists(model_name_1):
                raise FileNotFoundError(f"Model file not found: {model_name_1}")
            if not os.path.exists(model_name_2):
                raise FileNotFoundError(f"Model file not found: {model_name_2}")
            
            # Create models with less verbose output in MCP mode
            verbose_flag = not is_mcp_mode
            
            self.model_1 = Llama(
                model_path=model_name_1,
                n_gpu_layers=-1,
                n_ctx=0,
                flash_attn=True,
                logits_all=False,
                embedding=True,
                verbose=verbose_flag
            )
            self.model_2 = Llama(
                model_path=model_name_2,
                n_gpu_layers=-1,
                n_ctx=0,
                flash_attn=True,
                logits_all=False,
                embedding=True,
                verbose=verbose_flag
            )
        else:
            self.model_1 = SentenceTransformer(model_name_1,
                                         cache_folder="data/hub", 
                                         trust_remote_code=True).half().to(self.device)
            self.model_2 = SentenceTransformer(model_name_2,
                                         cache_folder="data/hub", 
                                         trust_remote_code=True).half().to(self.device)

    def get_embedding(self, text: str, is_query: bool = False):
        """
        Return the embedding (1-D list[float]) for a single sentence.
        """
        text_1 = text.strip()
        if is_query:
            text_2 = "query: " + text.strip()
        else:   
            text_2 = "passage: " + text.strip()
        if self.is_gguf:                                 
            emb_1 = self.model_1.create_embedding(text_1)["data"][0]["embedding"]
            emb_2 = self.model_2.create_embedding(text_2)["data"][0]["embedding"] 
            emb = np.add(emb_1, emb_2) 
            emb = _l2_normalize(emb)
            return emb
        else:                                             
            emb_1 = self.model_1.encode(
                [text], convert_to_numpy=True, device=self.device
            )[0]
            emb_2 = self.model_2.encode(
                [text], convert_to_numpy=True, device=self.device
            )[0]
            emb =  np.add(_l2_normalize(emb_1), _l2_normalize(emb_2)) 
            emb = _l2_normalize(emb)
            return emb.tolist()

    def get_embeddings(self, texts: list, is_query: bool = False):
        """
        Return embeddings (2-D numpy array) for multiple sentences.
        """
        texts_1 = [t.strip() for t in texts]
        if is_query:
            texts_2 = ["query: " + t.strip() for t in texts]
        else:
            texts_2 = ["passage: " + t.strip() for t in texts]
        if self.is_gguf:
            embs_1 = [self.model_1.create_embedding(t)["data"][0]["embedding"] for t in texts_1]
            embs_2 = [self.model_2.create_embedding(t)["data"][0]["embedding"] for t in texts_2]
            embs = np.add(_l2_normalize(embs_1), _l2_normalize(embs_2))  # element-wise sum
            embs = _l2_normalize(embs)       
            return embs
        else:
            embs_1 = self.model_1.encode(texts_1, convert_to_numpy=True, device=self.device)
            embs_2 = self.model_2.encode(texts_2, convert_to_numpy=True, device=self.device)
            embs = np.add(_l2_normalize(embs_1), _l2_normalize(embs_2))   # element-wise sum
            embs = _l2_normalize(embs)        
            return embs
# 기존 코드 (line 95-103) 대신:

if torch.cuda.is_available():
    device = "cuda"
elif torch.backends.mps.is_available():
    device = "mps"
else:
    device = "cpu"

# Lazy initialization
embedding_model = None

def get_embedding_model():
    """Get or create the embedding model instance"""
    global embedding_model
    if embedding_model is None:
        try:
            from docsray import MODEL_DIR
        except ImportError:
            MODEL_DIR = Path.home() / ".docsray" / "models"
        
        model_name_1 = str(MODEL_DIR / "bge-m3-gguf" / "bge-m3-Q8_0.gguf")
        model_name_2 = str(MODEL_DIR / "multilingual-e5-large-gguf" / "multilingual-e5-large-Q8_0.gguf")
        
        if not os.path.exists(model_name_1) or not os.path.exists(model_name_2):
            raise FileNotFoundError(
                f"Model files not found. Please run 'docsray download-models' first.\n"
                f"Expected locations:\n  {model_name_1}\n  {model_name_2}"
            )
        
        embedding_model = EmbeddingModel(model_name_1=model_name_1, model_name_2=model_name_2, device=device)
    
    return embedding_model

# For backward compatibility
try:
    embedding_model = get_embedding_model()
except:
    pass