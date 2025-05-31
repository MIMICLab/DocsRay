"""
DocsRay - PDF Question-Answering System with MCP Integration
"""

__version__ = "0.3.1"
__author__ = "Taehoon Kim"

import os
from pathlib import Path
os.environ["LLAMA_LOG_LEVEL"] = "40"  # Set log level to ERROR for Llama models

# Set up default paths
DOCSRAY_HOME = Path(os.environ.get("DOCSRAY_HOME", Path.home() / ".docsray"))
DATA_DIR = DOCSRAY_HOME / "data"
MODEL_DIR = DOCSRAY_HOME / "models"
CACHE_DIR = DOCSRAY_HOME / "cache"

import psutil

# (Optional) GPU VRAM 체크용
try:
    import torch
    has_cuda = torch.cuda.is_available()
except ImportError:
    has_cuda = False


def get_available_ram_gb():
    """Return available RAM in GB."""
    mem = psutil.virtual_memory()
    return mem.available / (1024 ** 3)

def get_min_gpu_vram_gb():
    """Return the minimum free GPU VRAM in GB across all visible GPUs."""
    import subprocess
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=memory.free', '--format=csv,nounits,noheader'],
            stdout=subprocess.PIPE,
            encoding='utf-8'
        )
        vram_list = [int(x) for x in result.stdout.strip().split('\n') if x]
        return min(vram_list) / 1024  # MB to GB
    except Exception:
        return None

# Determine available memory and adjust MAX_TOKENS accordingly
available_gb = get_available_ram_gb()
if has_cuda:
    vram_gb = get_min_gpu_vram_gb()
    if vram_gb is not None:
        available_gb = vram_gb

MAX_TOKENS = 32768  # Default value for high memory systems
FAST_MODE = False  # Default to normal mode
FULL_FEATURE_MODE = False  # Default to normal mode

if available_gb < 2:
    MAX_TOKENS = 4096  # Very low memory systems
    FAST_MODE = True  # Enable fast mode for very low memory systems

if available_gb < 4:
    FAST_MODE = True # Enable fast mode for low memory systems
    MAX_TOKENS = 8192  # Very low memory systems

elif available_gb < 8:
    MAX_TOKENS = 16384  # Low memory systems
elif available_gb > 32:
    MAX_TOKENS = 0
    FULL_FEATURE_MODE = True  # Enable full feature mode for high memory systems

print(f"MAX_TOKENS set to {MAX_TOKENS} (Available GB: {available_gb:.2f})")

# Create directories if they don't exist
for dir_path in [DOCSRAY_HOME, DATA_DIR, MODEL_DIR, CACHE_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# Conditional imports to avoid circular dependencies
__all__ = ["__version__", "DOCSRAY_HOME", "DATA_DIR", "MODEL_DIR", "CACHE_DIR"]

try:
    from .chatbot import PDFChatBot
    __all__.append("PDFChatBot")
except ImportError:
    pass  # During installation, dependencies might not be available yet