import os
import torch
import psutil
from pathlib import Path

# Paths
DOCSRAY_HOME = Path(os.environ.get("DOCSRAY_HOME", Path.home() / ".docsray"))
DATA_DIR = DOCSRAY_HOME / "data"
MODEL_DIR = DOCSRAY_HOME / "models"
CACHE_DIR = DOCSRAY_HOME / "cache"


try:
    import pytesseract
    USE_TESSERACT =True
except:
    print("Pytesseract not installed. Using gemma3 for OCR")
    USE_TESSERACT = False

# Create directories
for dir_path in [DOCSRAY_HOME, DATA_DIR, MODEL_DIR, CACHE_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

def get_available_ram_gb():
    mem = psutil.virtual_memory()
    return mem.available / (1024 ** 3)

def get_device_memory_gb():
    try:
        if torch.cuda.is_available():
            gpu_properties = torch.cuda.get_device_properties(0)
            total_memory = gpu_properties.total_memory / (1024**3)
            allocated_memory = torch.cuda.memory_allocated(0) / (1024**3)
            available_memory = total_memory - allocated_memory
            return available_memory, 'cuda'
        elif torch.backends.mps.is_available():
            available_memory = get_available_ram_gb()
            return available_memory * 0.8, 'mps'  
        else:
            # CPU only
            return get_available_ram_gb(), 'cpu'
    except Exception as e:
        print(e)
        return get_available_ram_gb(), 'cpu'


has_gpu = torch.cuda.is_available() or torch.backends.mps.is_available()
device_type = 'cpu'

available_gb, device_type = get_device_memory_gb()


FAST_MODE = False
MAX_TOKENS = 32768
STANDARD_MODE = False
FULL_FEATURE_MODE = False
min_available_gb = 8

if not has_gpu:
    FAST_MODE = True
    MAX_TOKENS = MAX_TOKENS // 2
else:
    if available_gb < min_available_gb * 2:
        FAST_MODE = True
        MAX_TOKENS = MAX_TOKENS // 2
    elif available_gb < min_available_gb * 3:
        STANDARD_MODE = True
        MAX_TOKENS = MAX_TOKENS         
    else:
        FULL_FEATURE_MODE = True

FAST_MODELS = []
STANDARD_MODELS = []
FULL_FEATURE_MODELS = []

ALL_MODELS = [
    {
        "dir": MODEL_DIR / "bge-m3-gguf",
        "file": "bge-m3-Q8_0.gguf",
        "url": "https://huggingface.co/tgisaturday/Docsray/resolve/main/bge-m3-gguf/bge-m3-Q8_0.gguf",
        "required": ["FAST_MODE", "STANDARD_MODE"]
    },
{
        "dir": MODEL_DIR / "bge-m3-gguf",
        "file": "bge-m3-F16.gguf",
        "url": "https://huggingface.co/tgisaturday/Docsray/resolve/main/bge-m3-gguf/bge-m3-F16.gguf",
        "required": ["FULL_FEATURE_MODE"]
    },
    {
        "dir": MODEL_DIR / "multilingual-e5-large-gguf",
        "file": "multilingual-e5-large-Q8_0.gguf",
        "url": "https://huggingface.co/tgisaturday/Docsray/resolve/main/multilingual-e5-large-gguf/multilingual-e5-large-Q8_0.gguf",
        "required": ["FAST_MODE", "STANDARD_MODE"]
    },
    {
        "dir": MODEL_DIR / "multilingual-e5-large-gguf",
        "file": "multilingual-e5-large-F16.gguf",
        "url": "https://huggingface.co/tgisaturday/Docsray/resolve/main/multilingual-e5-large-gguf/multilingual-e5-large-F16.gguf",
        "required": ["FULL_FEATURE_MODE"]
    },
    {
        "dir": MODEL_DIR / "gemma-3-1b-it-GGUF",
        "file": "gemma-3-1b-it-Q4_K_M.gguf",
        "url": "https://huggingface.co/tgisaturday/Docsray/resolve/main/gemma-3-1b-it-GGUF/gemma-3-1b-it-Q4_K_M.gguf",
        "required": ["FAST_MODE"]
    },
    {
        "dir": MODEL_DIR / "gemma-3-1b-it-GGUF",
        "file": "gemma-3-1b-it-Q8_0.gguf",
        "url": "https://huggingface.co/tgisaturday/Docsray/resolve/main/gemma-3-1b-it-GGUF/gemma-3-1b-it-Q8_0.gguf",
        "required": ["STANDARD_MODE"]
    },
    {
        "dir": MODEL_DIR / "gemma-3-1b-it-GGUF",
        "file": "gemma-3-1b-it-F16.gguf",
        "url": "https://huggingface.co/tgisaturday/Docsray/resolve/main/gemma-3-1b-it-GGUF/gemma-3-1b-it-F16.gguf",
        "required": ["FULL_FEATURE_MODE"]
    },
    {
        "dir": MODEL_DIR / "gemma-3-4b-it-GGUF",
        "file": "gemma-3-4b-it-Q4_K_M.gguf",
        "url": "https://huggingface.co/tgisaturday/Docsray/resolve/main/gemma-3-4b-it-GGUF/gemma-3-4b-it-Q4_K_M.gguf",
        "required": ["FAST_MODE"]
    },
    {
        "dir": MODEL_DIR / "gemma-3-4b-it-GGUF",
        "file": "gemma-3-4b-it-Q8_0.gguf",
        "url": "https://huggingface.co/tgisaturday/Docsray/resolve/main/gemma-3-4b-it-GGUF/gemma-3-4b-it-Q8_0.gguf",
        "required": ["STANDARD_MODE"]
    },
    {
        "dir": MODEL_DIR / "gemma-3-4b-it-GGUF",
        "file": "gemma-3-4b-it-F16.gguf",
        "url": "https://huggingface.co/tgisaturday/Docsray/resolve/main/gemma-3-4b-it-GGUF/gemma-3-4b-it-F16.gguf",
        "required": ["FULL_FEATURE_MODE"]
    },
    {
        "dir": MODEL_DIR / "gemma-3-4b-it-GGUF",
        "file": "mmproj-gemma-3-4b-it-F16.gguf",
        "url": "https://huggingface.co/tgisaturday/Docsray/resolve/main/gemma-3-4b-it-GGUF/mmproj-gemma-3-4b-it-F16.gguf",
        "required": ["FAST_MODE", "STANDARD_MODE", "FULL_FEATURE_MODE"]
    }
]

for model in ALL_MODELS:
    if "FAST_MODE" in model["required"]:
        FAST_MODELS.append(model)
    if "STANDARD_MODE" in model["required"]:
        STANDARD_MODELS.append(model)
    if "FULL_FEATURE_MODE" in model["required"]:
        FULL_FEATURE_MODELS.append(model)

DISABLE_VISUAL_ANALYSIS = os.environ.get("DOCSRAY_DISABLE_VISUALS", "0") == "1"

if os.environ.get("DOCSRAY_DEBUG", "0") == "1":
    print(f"Current Device: {device_type}")
    print(f"Available Memory: {available_gb:.2f} GB")
    print(f"FAST_MODE: {FAST_MODE}")
    print(f"MAX_TOKENS: {MAX_TOKENS}")
    print(f"FULL_FEATURE_MODE: {FULL_FEATURE_MODE}")