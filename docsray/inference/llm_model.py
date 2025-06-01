# src/inference/llm_model.py 

import torch
from llama_cpp import Llama

import os
import sys
from pathlib import Path
from docsray.config import FAST_MODE, FULL_FEATURE_MODE, MAX_TOKENS
import base64
import io
from PIL import Image
from contextlib import redirect_stderr
from llama_cpp.llama_chat_format import Gemma3ChatHandler


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

def image_to_base64_data_uri(image: Image.Image, format: str = "JPEG", quality: int = 85) -> str:
    """Convert PIL Image to base64 data URI."""
    buffered = io.BytesIO()
    image.save(buffered, format=format, quality=quality, optimize=True)
    img_base64 = base64.b64encode(buffered.getvalue()).decode('utf-8')
    mime_type = f"image/{format.lower()}"
    return f'data:{mime_type};base64,{img_base64}'
    
class LocalLLM:
    def __init__(self, model_name="google/gemma-3-1b-it", device="gpu", is_multimodal=False):
        self.device = device
        self.is_multimodal = is_multimodal
        
        # Convert relative path to absolute path
        if not os.path.isabs(model_name):
            current_dir = Path(__file__).parent.absolute()
            project_root = current_dir.parent.parent  # Go up two levels
            model_name = str(project_root / model_name)

        # Check if file exists
        if not os.path.exists(model_name):
            raise FileNotFoundError(f"Model file not found: {model_name}")
        
            
        with open(os.devnull, 'w') as devnull:
            with redirect_stderr(devnull):
                # For multimodal models, look for mmproj file
                self.mmproj_path = None
                chat_handler = None
                if is_multimodal and "gemma" in model_name.lower():
                    model_dir = Path(model_name).parent
                    mmproj_files = list(model_dir.glob("*mmproj*.gguf"))        
                    self.mmproj_path = str(mmproj_files[0])
                    chat_handler = Gemma3ChatHandler(clip_model_path=self.mmproj_path, verbose=False) 

                
                self.model = Llama( 
                                    model_path=model_name,
                                    n_gpu_layers= -1,
                                    n_ctx = MAX_TOKENS,
                                    verbose=False,
                                    flash_attn=True,
                                    chat_handler=chat_handler
                                )
                self.tokenizer = LlamaTokenizer(self.model)

    def generate(self, prompt, image=None):
        """
        Generate text from prompt, optionally with an image for multimodal models.
        
        Args:
            prompt: Text prompt
            image: PIL Image object (optional)
        """
        if image is not None and self.is_multimodal and self.mmproj_path:
            # Use chat completion API for multimodal input
            
            # Convert to RGB if necessary
            if image.mode in ('RGBA', 'LA'):
                rgb_image = Image.new('RGB', image.size, (255, 255, 255))
                rgb_image.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = rgb_image
            elif image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Convert image to data URI
            image_uri = image_to_base64_data_uri(image, format="PNG")
            messages = [
                {
                    "role": "user",
                    "content": [
                                {'type': 'text', 'text': prompt},
                                {'type': 'image_url', 'image_url': image_uri},
                    ]
                }
            ]
            
            # Calculate max tokens for output
            available_tokens = MAX_TOKENS if MAX_TOKENS > 0 else 131072
            output_tokens = min(8192, available_tokens // 4)
            
            # Generate response
            try:
                response = self.model.create_chat_completion(
                    messages=messages,
                    max_tokens=output_tokens,
                    stop = ['<end_of_turn>'],
                    temperature=0.7,
                    top_p=0.95,
                    repeat_penalty=1.1
                )
                result = response['choices'][0]['message']['content']
                return result.strip()
                
            except Exception as e:
                print(f"Error in multimodal generation: {e}", file=sys.stderr)
                import traceback
                traceback.print_exc()
                # Fallback to text-only
                print("Falling back to text-only generation", file=sys.stderr)
                return self.generate(prompt, image=None)
        
        else:
            # Text-only generation
            if "gemma" in self.model.model_path.lower():
                formatted_prompt = f"<start_of_turn>user\n{prompt}<end_of_turn>\n<start_of_turn>model\n"
                stop = ['<end_of_turn>']
            else:
                formatted_prompt = f"<|im_start|>user\n{prompt}<|im_end|><|im_start|>assistant\n"
                stop = ['<|im_end|>']
            
            output_tokens = MAX_TOKENS if MAX_TOKENS > 0 else 8192
            
            answer = self.model(
                formatted_prompt,
                max_tokens=output_tokens,
                stop=stop,
                echo=True,
                temperature=0.7,
                top_p=0.95,
                repeat_penalty=1.1,
            )
            
            result = answer['choices'][0]['text']

            return result.strip()
    
    def strip_response(self, response):
        """Extract the model's response from the full generated text."""
        if not response:
            return response
            
        if "gemma" in self.model.model_path.lower():
            if '<start_of_turn>model' in response:
                response = response.split('<start_of_turn>model')[-1]
            if '<end_of_turn>' in response:
                response = response.split('<end_of_turn>')[0]
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
            local_llm_large = local_llm  

        elif FAST_MODE:
            print("Running in fast mode. Using smaller model for inference.")
            local_llm = LocalLLM(model_name=str(MODEL_DIR / "gemma-3-1b-it-GGUF" / "gemma-3-1b-it-Q4_K_M.gguf"), device=device)
            local_llm_large = LocalLLM(model_name=str(MODEL_DIR / "gemma-3-4b-it-GGUF" / "gemma-3-4b-it-Q4_K_M.gguf"), device=device, is_multimodal=True)
        else:
            # Standard mode: 4B model with multimodal capabilities
            local_llm = LocalLLM(model_name=small_model_path, device=device)            
            local_llm_large = LocalLLM(model_name=large_model_path, device=device, is_multimodal=True)
    
    return local_llm, local_llm_large

# For backward compatibility
try:
    local_llm, local_llm_large = get_llm_models()
except:
    pass