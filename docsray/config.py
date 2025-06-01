import os
import torch
import psutil
from pathlib import Path

# Paths
DOCSRAY_HOME = Path(os.environ.get("DOCSRAY_HOME", Path.home() / ".docsray"))
DATA_DIR = DOCSRAY_HOME / "data"
MODEL_DIR = DOCSRAY_HOME / "models"
CACHE_DIR = DOCSRAY_HOME / "cache"

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


has_gpu = False
device_type = 'cpu'
try:
    has_gpu = torch.cuda.is_available() or torch.backends.mps.is_available()
    if torch.cuda.is_available():
        device_type = 'cuda'
    elif torch.backends.mps.is_available():
        device_type = 'mps'
except ImportError:
    pass

available_gb, detected_device = get_device_memory_gb()


FAST_MODE = False
MAX_TOKENS = 32768
FULL_FEATURE_MODE = False

if not has_gpu:
    FAST_MODE = True
    MAX_TOKENS = 8192
else:
    if device_type == 'cuda':
        if available_gb < 8:
            FAST_MODE = True
            MAX_TOKENS = 16384
        elif available_gb < 16:
            MAX_TOKENS = 16384
        elif available_gb < 32:
            MAX_TOKENS = 32768
        else:
            MAX_TOKENS = 0  
            FULL_FEATURE_MODE = True
    elif device_type == 'mps':
        if available_gb < 8:
            FAST_MODE = True
            MAX_TOKENS = 16384
        elif available_gb < 16:
            MAX_TOKENS = 16384
        elif available_gb < 32:
            MAX_TOKENS = 32768
        else:
            MAX_TOKENS = 0  
            FULL_FEATURE_MODE = True

DISABLE_VISUAL_ANALYSIS = os.environ.get("DOCSRAY_DISABLE_VISUALS", "0") == "1"

if os.environ.get("DOCSRAY_DEBUG", "0") == "1":
    print(f"장치: {detected_device}")
    print(f"사용 가능 메모리: {available_gb:.2f} GB")
    print(f"FAST_MODE: {FAST_MODE}")
    print(f"MAX_TOKENS: {MAX_TOKENS}")
    print(f"FULL_FEATURE_MODE: {FULL_FEATURE_MODE}")