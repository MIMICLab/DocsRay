from __future__ import annotations
import mteb
import numpy as np
from sentence_transformers import SentenceTransformer
import torch
import numpy as np
from typing import List

EPS = 1e-8              

class EmbeddingModel:
    def __init__(self, device: str = "cpu"):
        """
        Initialize embedding models with caching support.
        
        Args:
            device: Device to run models on ("cpu", "cuda", "mps")
            cache_size: Number of embeddings to cache
        """
        # Initialize models
        self.model_1 = SentenceTransformer(
            "BAAI/bge-m3", 
            trust_remote_code=True,
            model_kwargs={"torch_dtype": torch.float16}
        )
        self.model_2 = SentenceTransformer(
            "intfloat/multilingual-e5-large", 
            trust_remote_code=True,
            model_kwargs={"torch_dtype": torch.float16}
        )        
        self.device = device        

        # Move models to device
        if device in ["cuda", "mps"]:
            self.model_1.to(self.device)
            self.model_2.to(self.device)
        
    
    def get_embedding(self, text: str, is_query: bool = False) -> List[float]:
        """
        Get embedding for a single text with caching.
        
        Args:
            text: Input text
            is_query: Whether this is a query (True) or passage (False)
        
        Returns:
            Embedding as list of floats
        """
        text_1 = text.strip()
        if is_query:
            text_2 = "query: " + text.strip()
        else:   
            text_2 = "passage: " + text.strip()

        # Generate embeddings
        with torch.no_grad():
            emb_1 = self.model_1.encode(
                [text_1], 
                convert_to_numpy=True, 
                device=self.device,
                normalize_embeddings=True
            )[0]
            emb_2 = self.model_2.encode(
                [text_2], 
                convert_to_numpy=True, 
                device=self.device,
                normalize_embeddings=True
            )[0]
        
        # Combine embeddings
        emb = np.add(emb_1, emb_2)
        emb = emb / (np.linalg.norm(emb) + EPS)  # L2 normalization
        
        return emb

    def get_embeddings(self, texts: List[str], is_query: bool = False) -> List[List[float]]:
        """
        Get embeddings for multiple texts with batch processing and caching.
        
        Args:
            texts: List of input texts
            is_query: Whether these are queries (True) or passages (False)
        
        Returns:
            List of embeddings
        """
        if not texts:
            return []
        
        # Process uncached texts in batch
        texts_1 = [t.strip() for t in texts]
        if is_query:
            texts_2 = ["query: " + t.strip() for t in texts]
        else:
            texts_2 = ["passage: " + t.strip() for t in texts]
        
        # Batch encode
        with torch.no_grad():
            embs_1 = self.model_1.encode(
                texts_1, 
                convert_to_numpy=True, 
                device=self.device,
                normalize_embeddings=True,
                show_progress_bar=False
            )
            embs_2 = self.model_2.encode(
                texts_2, 
                convert_to_numpy=True, 
                device=self.device,
                normalize_embeddings=True,
                show_progress_bar=False
            )
        
        # Combine embeddings
        combined_embs = np.add(embs_1, embs_2)
        combined_embs = combined_embs / (np.linalg.norm(combined_embs, axis=1, keepdims=True) + EPS)    
        
        return combined_embs
    


class DocsrayEmbedding:
    def __init__(self):
        super().__init__()
        # Global instance
        if torch.cuda.is_available():
            device = "cuda"
        elif torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"

        # Initialize with larger cache for production use
        self.embedding_model = EmbeddingModel(device=device)
    def encode(
        self,
        sentences: list[str],
        *,
        task_name: str,
        prompt_type=None,
        **kwargs
    ) -> np.ndarray:
        # your custom implementation here
        return self.embedding_model.get_embeddings(sentences)

if __name__ == "__main__":
    # Example usage
    model = DocsrayEmbedding()
    benchmark = mteb.get_benchmark("MTEB(Multilingual, v2)")
    tasks = mteb.get_tasks(tasks=benchmark)
    evaluation = mteb.MTEB(tasks=tasks)
    evaluation.run(model)