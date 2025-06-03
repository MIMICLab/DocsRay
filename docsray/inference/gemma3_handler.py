#borrowed from https://github.com/kossum/llama-cpp-python/blob/main/llama_cpp/llama_chat_format.py
from __future__ import annotations
from PIL import Image
import math
import io

import ctypes
from typing import (
    List,
    Literal,
    Tuple,
)
import llama_cpp.llama as llama

import llama_cpp
from llama_cpp.llama_chat_format import Llava15ChatHandler

class Gemma3ChatHandler(Llava15ChatHandler):
    # Chat Format:
    # '<bos><start_of_turn>user\n{system_prompt}\n\n{prompt}<end_of_turn>\n<start_of_turn>model\n'

    DEFAULT_SYSTEM_MESSAGE = None

    CHAT_FORMAT = (
        "{{ '<bos>' }}"
        "{%- if messages[0]['role'] == 'system' -%}"
        "{%- if messages[0]['content'] is string -%}"
        "{%- set first_user_prefix = messages[0]['content'] + '\n\n' -%}"
        "{%- else -%}"
        "{%- set first_user_prefix = messages[0]['content'][0]['text'] + '\n\n' -%}"
        "{%- endif -%}"
        "{%- set loop_messages = messages[1:] -%}"
        "{%- else -%}"
        "{%- set first_user_prefix = \"\" -%}"
        "{%- set loop_messages = messages -%}"
        "{%- endif -%}"
        "{%- for message in loop_messages -%}"
        "{%- if (message['role'] == 'user') != (loop.index0 % 2 == 0) -%}"
        "{{ raise_exception(\"Conversation roles must alternate user/assistant/user/assistant/...\") }}"
        "{%- endif -%}"
        "{%- if (message['role'] == 'assistant') -%}"
        "{%- set role = \"model\" -%}"
        "{%- else -%}"
        "{%- set role = message['role'] -%}"
        "{%- endif -%}"
        "{{ '<start_of_turn>' + role + '\n' + (first_user_prefix if loop.first else \"\") }}"
        "{%- if message['content'] is string -%}"
        "{{ message['content'] | trim }}"
        "{%- elif message['content'] is iterable -%}"
        "{%- for item in message['content'] -%}"
        "{%- if item['type'] == 'image_url' -%}"
        "{{ '<start_of_image>' }}"
        "{%- elif item['type'] == 'text' -%}"
        "{{ item['text'] | trim }}"
        "{%- endif -%}"
        "{%- endfor -%}"
        "{%- else -%}"
        "{{ raise_exception(\"Invalid content type\") }}"
        "{%- endif -%}"
        "{{ '<end_of_turn>\n' }}"
        "{%- endfor -%}"
        "{%- if add_generation_prompt -%}"
        "{{ '<start_of_turn>model\n' }}"
        "{%- endif -%}"
    )

    @staticmethod
    def split_text_on_image_urls(text: str, image_urls: List[str]):
        split_text: List[Tuple[Literal["text", "image_url"], str]] = []
        copied_urls = image_urls[:]
        remaining = text
        image_placeholder = "<start_of_image>"

        while remaining:
            # Find placeholder
            pos = remaining.find(image_placeholder)
            if pos != -1:
                assert len(copied_urls) > 0
                if pos > 0:
                    split_text.append(("text", remaining[:pos]))
                split_text.append(("text", "\n\n<start_of_image>"))
                split_text.append(("image_url", copied_urls.pop(0)))
                split_text.append(("text", "<end_of_image>\n\n"))
                remaining = remaining[pos + len(image_placeholder):]
            else:
                assert len(copied_urls) == 0
                split_text.append(("text", remaining))
                remaining = ""
        return split_text

    def eval_image(self, llama: llama.Llama, image_url: str):

        n_tokens = 256
        if llama.n_tokens + n_tokens > llama.n_ctx():
            raise ValueError(
                f"Prompt exceeds n_ctx: {llama.n_tokens + n_tokens} > {llama.n_ctx()}"
            )

        img_bytes = self.load_image(image_url)
        img_u8_p = self._llava_cpp.clip_image_u8_init()
        if not self._llava_cpp.clip_image_load_from_bytes(
            ctypes.create_string_buffer(img_bytes, len(img_bytes)),
            ctypes.c_size_t(len(img_bytes)),
            img_u8_p,
        ):
            self._llava_cpp.clip_image_u8_free(img_u8_p)
            raise ValueError("Failed to load image.")

        img_f32 = self._llava_cpp.clip_image_f32_batch()
        img_f32_p = ctypes.byref(img_f32)
        if not self._llava_cpp.clip_image_preprocess(self.clip_ctx, img_u8_p, img_f32_p):
            self._llava_cpp.clip_image_f32_batch_free(img_f32_p)
            self._llava_cpp.clip_image_u8_free(img_u8_p)
            raise ValueError("Failed to preprocess image.")

        n_embd = llama_cpp.llama_model_n_embd(llama._model.model)
        embed = (ctypes.c_float * (n_tokens * n_embd))()
        if not self._llava_cpp.clip_image_batch_encode(self.clip_ctx, llama.n_threads, img_f32_p, embed):
            self._llava_cpp.clip_image_f32_batch_free(img_f32_p)
            self._llava_cpp.clip_image_u8_free(img_u8_p)
            raise ValueError("Failed to encode image.")

        self._llava_cpp.clip_image_f32_batch_free(img_f32_p)
        self._llava_cpp.clip_image_u8_free(img_u8_p)
        llama_cpp.llama_set_causal_attn(llama.ctx, False)

        seq_id_0 = (ctypes.c_int32 * 1)()
        seq_ids = (ctypes.POINTER(ctypes.c_int32) * (n_tokens + 1))()
        for i in range(n_tokens):
            seq_ids[i] = seq_id_0

        batch = llama_cpp.llama_batch()
        batch.n_tokens = n_tokens
        batch.token = None
        batch.embd = embed
        batch.pos = (ctypes.c_int32 * n_tokens)(*[i + llama.n_tokens for i in range(n_tokens)])
        batch.seq_id = seq_ids
        batch.n_seq_id = (ctypes.c_int32 * n_tokens)(*([1] * n_tokens))
        batch.logits = (ctypes.c_int8 * n_tokens)()

        if llama_cpp.llama_decode(llama.ctx, batch):
            raise ValueError("Failed to decode image.")

        llama_cpp.llama_set_causal_attn(llama.ctx, True)
        # Required to avoid issues with hf tokenizer
        llama.input_ids[llama.n_tokens : llama.n_tokens + n_tokens] = -1
        llama.n_tokens += n_tokens

def merge_images_to_grid(pil_images, padding=10, bg_color=(255, 255, 255)):
    """
    Merge multiple PIL Image objects into a single grid
    
    Args:
        pil_images: List of PIL Image objects
        padding: Padding between images (pixels)
        bg_color: Background color (RGB tuple)
    
    Returns:
        PIL Image object
    """
    if not pil_images:
        print("No images provided.")
        return None
    
    # Convert image mode if necessary
    images = []
    for img in pil_images:
        if img.mode != 'RGB':
            img = img.convert('RGB')
        images.append(img)
    
    num_images = len(images)
    
    # Calculate optimal grid size (close to square or 4:3 ratio)
    cols, rows = calculate_optimal_grid(num_images)
    
    # Find maximum dimensions among all images
    max_width = max(img.width for img in images)
    max_height = max(img.height for img in images)
    
    # Calculate total canvas size
    canvas_width = cols * max_width + (cols - 1) * padding
    canvas_height = rows * max_height + (rows - 1) * padding
    
    # Create new image
    merged_image = Image.new('RGB', (canvas_width, canvas_height), bg_color)
    
    # Place images on grid
    for idx, img in enumerate(images):
        row = idx // cols
        col = idx % cols
        
        # Calculate image position (center aligned)
        x = col * (max_width + padding) + (max_width - img.width) // 2
        y = row * (max_height + padding) + (max_height - img.height) // 2
        
        merged_image.paste(img, (x, y))

    return merged_image

def calculate_optimal_grid(num_images):
    """
    Calculate grid size closest to square or 4:3 aspect ratio
    """
    # Grid close to square
    sqrt_n = math.sqrt(num_images)
    cols_square = math.ceil(sqrt_n)
    rows_square = math.ceil(num_images / cols_square)
    
    # Grid with 4:3 aspect ratio
    # cols : rows = 4 : 3, so cols = 4k, rows = 3k
    # Find minimum k where cols * rows >= num_images
    k = math.ceil(math.sqrt(num_images / 12))
    cols_ratio = 4 * k
    rows_ratio = 3 * k
    
    # Adjust actual number of rows needed
    while cols_ratio * rows_ratio < num_images:
        if cols_ratio * (rows_ratio + 1) >= num_images:
            rows_ratio += 1
        else:
            k += 1
            cols_ratio = 4 * k
            rows_ratio = 3 * k
    
    # Choose better ratio (less empty space)
    empty_square = cols_square * rows_square - num_images
    empty_ratio = cols_ratio * rows_ratio - num_images
    
    if empty_square <= empty_ratio:
        return cols_square, rows_square
    else:
        return cols_ratio, rows_ratio

def resize_images_uniform(pil_images, target_size=(800, 600)):
    """
    Resize all images to uniform size
    
    Args:
        pil_images: List of PIL Image objects
        target_size: Target size (width, height)
    
    Returns:
        List of resized PIL Image objects
    """
    resized_images = []
    for img in pil_images:
        # Resize maintaining aspect ratio
        img_copy = img.copy()
        img_copy.thumbnail(target_size, Image.Resampling.LANCZOS)
        
        # Add padding to match exact target_size
        new_img = Image.new('RGB', target_size, (255, 255, 255))
        x = (target_size[0] - img_copy.width) // 2
        y = (target_size[1] - img_copy.height) // 2
        new_img.paste(img_copy, (x, y))
        
        resized_images.append(new_img)
    
    return resized_images