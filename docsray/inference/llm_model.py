# src/inference/llm_model.py 

import torch
from docsray import MAX_TOKENS
from llama_cpp import Llama
import os
import sys
from pathlib import Path
from docsray import FAST_MODE, FULL_FEATURE_MODE, MAX_TOKENS
import base64
import io
from PIL import Image

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
    def __init__(self, model_name="google/gemma-3-1b-it", device="gpu", is_multimodal=False):
        self.device = device
        self.is_multimodal = is_multimodal
        
        # Convert relative path to absolute path
        if not os.path.isabs(model_name):
            current_dir = Path(__file__).parent.absolute()
            project_root = current_dir.parent.parent  # Go up two levels
            model_name = str(project_root / model_name)
        
        # Check if we're in MCP mode (less verbose)
        is_mcp_mode = os.getenv('DOCSRAY_MCP_MODE') == '1'
        
        if not is_mcp_mode:
            print(f"Loading LLM from: {model_name}", file=sys.stderr)
            if is_multimodal:
                print(f"Multimodal mode enabled for vision tasks", file=sys.stderr)
        
        # Check if file exists
        if not os.path.exists(model_name):
            raise FileNotFoundError(f"Model file not found: {model_name}")
        
        # Initialize model with appropriate settings
        model_kwargs = {
            "model_path": model_name,
            "n_gpu_layers": -1,
            "n_ctx": MAX_TOKENS,
            "no_perf": True,
            "logits_all": False,
            "verbose": False
        }
        
        # For multimodal Gemma models, we need special handling
        if is_multimodal and "gemma" in model_name.lower() and "4b" in model_name.lower():
            # Gemma-3-4B multimodal uses a specific chat handler
            # Note: This assumes the model has vision capabilities built-in
            model_kwargs["chat_handler"] = None  # Will handle formatting ourselves
            model_kwargs["clip_model_path"] = None  # Gemma has integrated vision
        
        self.model = Llama(**model_kwargs)
        self.tokenizer = LlamaTokenizer(self.model)

    def generate(self, prompt, image=None):
        """
        Generate text from prompt, optionally with an image for multimodal models.
        
        Args:
            prompt: Text prompt
            image: PIL Image object (optional)
        """
        # Format prompt based on model type
        if "gemma" in self.model.model_path.lower():
            if image is not None and self.is_multimodal:
                # Determine max image size based on context window
                if FULL_FEATURE_MODE and MAX_TOKENS == 0:
                    # Full context window available - use maximum quality
                    max_size = (896, 896)
                    jpeg_quality = 90
                    fallback_size = (672, 672)
                elif MAX_TOKENS >= 32768:
                    # Large context window
                    max_size = (672, 672)
                    jpeg_quality = 85
                    fallback_size = (448, 448)
                elif MAX_TOKENS >= 16384:
                    # Limited context window - be more conservative
                    max_size = (336, 336)  # Start smaller
                    jpeg_quality = 75
                    fallback_size = (224, 224)
                else:
                    # Very limited context
                    max_size = (224, 224)
                    jpeg_quality = 70
                    fallback_size = (168, 168)
                
                # Calculate new size maintaining aspect ratio
                if image.width > max_size[0] or image.height > max_size[1]:
                    image.thumbnail(max_size, Image.Resampling.LANCZOS)
                
                # Convert to RGB if necessary (remove alpha channel)
                if image.mode in ('RGBA', 'LA'):
                    rgb_image = Image.new('RGB', image.size, (255, 255, 255))
                    rgb_image.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                    image = rgb_image
                elif image.mode != 'RGB':
                    image = image.convert('RGB')
                
                # First attempt with current size
                buffered = io.BytesIO()
                image.save(buffered, format="JPEG", quality=jpeg_quality, optimize=True)
                img_base64 = base64.b64encode(buffered.getvalue()).decode()
                
                # More accurate token estimation for base64 encoded images
                # Base64 increases size by ~33%, and each token is ~4 chars
                # Plus Gemma template overhead
                template_overhead = 150  # Increased overhead estimate
                estimated_tokens = (len(img_base64) // 3) + (len(prompt) // 4) + template_overhead
                available_tokens = MAX_TOKENS if MAX_TOKENS > 0 else 32768
                
                # For 16384 context, be extra conservative
                if MAX_TOKENS == 16384:
                    target_usage = 0.4  # Only use 40% for prompt+image
                else:
                    target_usage = 0.6  # Use 60% for larger contexts
                
                if estimated_tokens > available_tokens * target_usage:
                    # Reduce size more aggressively
                    image.thumbnail(fallback_size, Image.Resampling.LANCZOS)
                    buffered = io.BytesIO()
                    image.save(buffered, format="JPEG", quality=jpeg_quality-10, optimize=True)
                    img_base64 = base64.b64encode(buffered.getvalue()).decode()
                    
                    # Check again
                    estimated_tokens = (len(img_base64) // 3) + (len(prompt) // 4) + template_overhead
                    if estimated_tokens > available_tokens * target_usage:
                        # Final attempt with very small size
                        final_size = (168, 168) if MAX_TOKENS >= 16384 else (112, 112)
                        image.thumbnail(final_size, Image.Resampling.LANCZOS)
                        buffered = io.BytesIO()
                        image.save(buffered, format="JPEG", quality=65, optimize=True)
                        img_base64 = base64.b64encode(buffered.getvalue()).decode()
                        
                        # Log the final size for debugging
                        final_tokens = (len(img_base64) // 3) + (len(prompt) // 4) + template_overhead
                        print(f"Image resized to {image.size}, estimated tokens: {final_tokens}/{available_tokens}", file=sys.stderr)
                
                # Gemma-3 multimodal format with proper template
                formatted_prompt = f"<start_of_turn>user\n{prompt}\n<start_of_image>\n<img src=\"data:image/jpeg;base64,{img_base64}\"><end_of_turn>\n<start_of_turn>model\n"
            else:
                # Standard Gemma text-only format
                formatted_prompt = f"<start_of_turn>user\n{prompt}<end_of_turn>\n<start_of_turn>model\n"
            stop = ['<end_of_turn>']
        else:
            # Other models (e.g., LLaMA format)
            if image is not None and self.is_multimodal:
                # Use same conservative approach for other models
                if MAX_TOKENS >= 32768:
                    max_size = (448, 448)
                    jpeg_quality = 80
                elif MAX_TOKENS >= 16384:
                    max_size = (336, 336)
                    jpeg_quality = 75
                else:
                    max_size = (224, 224)
                    jpeg_quality = 70
                
                image.thumbnail(max_size, Image.Resampling.LANCZOS)
                
                if image.mode in ('RGBA', 'LA'):
                    rgb_image = Image.new('RGB', image.size, (255, 255, 255))
                    rgb_image.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                    image = rgb_image
                elif image.mode != 'RGB':
                    image = image.convert('RGB')
                
                buffered = io.BytesIO()
                image.save(buffered, format="JPEG", quality=jpeg_quality, optimize=True)
                img_base64 = base64.b64encode(buffered.getvalue()).decode()
                
                formatted_prompt = f"<|im_start|>user\n<image>{img_base64}</image>\n{prompt}<|im_end|><|im_start|>assistant\n"
            else:
                formatted_prompt = f"<|im_start|>user\n{prompt}<|im_end|><|im_start|>assistant\n"
            stop = ['<|im_end|>']
        
        # Generate response
        # Adjust max output tokens based on how much context we used
        if image is not None:
            # Very conservative output tokens for image inputs
            if MAX_TOKENS == 16384:
                output_tokens = 1024  # Very limited
            elif MAX_TOKENS > 0:
                output_tokens = min(2048, int(MAX_TOKENS * 0.25))
            else:
                output_tokens = 2048
        else:
            output_tokens = MAX_TOKENS if MAX_TOKENS > 0 else 4096
            
        answer = self.model(
            formatted_prompt,
            max_tokens=output_tokens,
            stop=stop,
            echo=True,  # Include the prompt in the response
            temperature=0.7,
            top_p=0.95,
            repeat_penalty=1.1,
        )
        
        result = answer['choices'][0]['text']
        print(result, file=sys.stderr)  # Log the full response for debugging
        return result.strip()
    
    def strip_response(self, response):
        """Extract the model's response from the full generated text."""
        if "gemma" in self.model.model_path.lower():
            # Handle both with and without image tags
            if '<start_of_turn>model' in response:
                response = response.split('<start_of_turn>model')[-1]
            if '<end_of_turn>' in response:
                response = response.split('<end_of_turn>')[0]
            # Also remove any trailing newlines from the formatted response
            return response.strip().lstrip('\n')
        else:
            if '<|im_start|>assistant' in response:
                response = response.split('<|im_start|>assistant')[-1]
            if '<|im_end|>' in response:
                response = response.split('<|im_end|>')[0]
            return response.strip()


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
        large_model_path = str(MODEL_DIR / "gemma-3-4b-it-GGUF" / "gemma-3-4b-it-Q8_0.gguf")
        
        if not os.path.exists(small_model_path) or not os.path.exists(large_model_path):
            raise FileNotFoundError(
                f"Model files not found. Please run 'docsray download-models' first.\n"
                f"Expected locations:\n  {small_model_path}\n  {large_model_path}"
            )
        
        if FULL_FEATURE_MODE:
            print("Running in full feature mode. Using larger model for inference.")
            # In full feature mode, use 4B model for everything including multimodal
            local_llm = LocalLLM(model_name=large_model_path, device=device, is_multimodal=True)
        else:
            # Standard mode: 1B for text, 4B for multimodal
            local_llm = LocalLLM(model_name=small_model_path, device=device, is_multimodal=False)
            
        if FAST_MODE:
            print("Running in fast mode. Using smaller model for inference.")
            # In fast mode, use the same small model for both
            local_llm_large = local_llm
        else:
            # Standard mode: 4B model with multimodal capabilities
            local_llm_large = LocalLLM(model_name=large_model_path, device=device, is_multimodal=True)
    
    return local_llm, local_llm_large

# For backward compatibility
try:
    local_llm, local_llm_large = get_llm_models()
except:
    pass