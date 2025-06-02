# src/inference/llm_model.py 

import torch
from llama_cpp import Llama

import os
import sys
from pathlib import Path
from docsray.config import FAST_MODE, STANDARD_MODE, FULL_FEATURE_MODE, MAX_TOKENS
from docsray.config import ALL_MODELS, FAST_MODELS, STANDARD_MODELS, FULL_FEATURE_MODELS

import base64
import io
from PIL import Image
from contextlib import redirect_stderr
from llama_cpp.llama_chat_format import Gemma3ChatHandler

def get_gemma_model_paths(mode_models):
    small_model_path = None
    large_model_path = None
    mmproj_path = None
    for model in mode_models:
        if "gemma-3-1b-it" in model["file"] and "mmproj" not in model["file"]:
            small_model_path = str(model["dir"] / model["file"])
        elif "gemma-3-4b-it" in model["file"] and "mmproj" not in model["file"]:
            large_model_path = str(model["dir"] / model["file"])
        elif "mmproj" in model["file"]:
            mmproj_path = str(model["dir"] / model["file"])
    
    return small_model_path, large_model_path, mmproj_path

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
    def __init__(self, model_name=None, mmproj_name=None, device="gpu", is_multimodal=False):
        self.device = device
        self.is_multimodal = is_multimodal
        self.model_name = model_name
        self.mmproj_name = mmproj_name

        # Convert relative path to absolute path
        if not os.path.isabs(model_name):
            current_dir = Path(__file__).parent.absolute()
            project_root = current_dir.parent.parent  # Go up two levels
            self.model_name = str(project_root / model_name)

        self.mmproj_path = None
        chat_handler = None
        
        if is_multimodal and "gemma" in model_name.lower():
            if not os.path.isabs(mmproj_name):
                # If relative path, resolve it relative to model directory
                model_dir = Path(model_name).parent
                self.mmproj_name = str(model_dir / mmproj_name)
            
            chat_handler = Gemma3ChatHandler(clip_model_path=self.mmproj_name, 
                                             verbose=False)
        with open(os.devnull, 'w') as devnull:
            with redirect_stderr(devnull):
                self.model = Llama( 
                    model_path=model_name,
                    n_gpu_layers=-1,
                    n_ctx=MAX_TOKENS,
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
        if image is not None and self.is_multimodal:
            # Use chat completion API for multimodal input
            
            # Convert to RGB if necessary
            if image.mode in ('RGBA', 'LA'):
                rgb_image = Image.new('RGB', image.size, (255, 255, 255))
                rgb_image.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = rgb_image
            elif image.mode != 'RGB':
                image = image.convert('RGB')

            if FULL_FEATURE_MODE:
                w, h = image.size
                if w < h:
                    new_w = 896
                    new_h = int(h * (896 / w))
                else:
                    new_h = 896
                    new_w = int(w * (896 / h))
                resized = image.resize((new_w, new_h), Image.LANCZOS)
            else:
                resized = image.resize((896, 896), Image.LANCZOS)

            # Convert image to data URI
            image_uri = image_to_base64_data_uri(resized, format="PNG")
            messages = [
                {
                    "role": "user",
                    "content": [
                                {'type': 'text', 'text': prompt},
                                {'type': 'image_url', 'image_url': image_uri},
                    ]
                }
            ]
            response = self.model.create_chat_completion(
                messages=messages,
                stop = ['<end_of_turn>'],
                temperature=0.7,
                top_p=0.95,
                repeat_penalty=1.1
            )
            result = response['choices'][0]['message']['content']  

            return result.strip()
        
        else:
            # Text-only generation
            if "gemma" in self.model.model_path.lower():
                formatted_prompt = f"<start_of_turn>user\n{prompt}<end_of_turn>\n<start_of_turn>model\n"
                stop = ['<end_of_turn>']
            else:
                formatted_prompt = f"<|im_start|>user\n{prompt}<|im_end|><|im_start|>assistant\n"
                stop = ['<|im_end|>']
            
            answer = self.model(
                formatted_prompt,
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

def get_llm_models():
    """Get or create the LLM model instances"""
    if FAST_MODE:
        small_model_path, large_model_path, mmproj_path = get_gemma_model_paths(FAST_MODELS)
    elif STANDARD_MODE: 
        small_model_path, large_model_path, mmproj_path = get_gemma_model_paths(STANDARD_MODELS)
    else:
        small_model_path, large_model_path, mmproj_path = get_gemma_model_paths(FULL_FEATURE_MODELS)
    
    local_llm = LocalLLM(model_name=small_model_path, device=device)            
    local_llm_large = LocalLLM(model_name=large_model_path, mmproj_name=mmproj_path, device=device, is_multimodal=True)
    
    return local_llm, local_llm_large


local_llm, local_llm_large = get_llm_models()
