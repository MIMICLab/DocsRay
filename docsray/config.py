# docsray/config.py
import os
import psutil

# Configuration constants
MAX_TOKENS = 32768
FAST_MODE = False
FULL_FEATURE_MODE = False

# Memory detection
def get_available_ram_gb():
    """Return available RAM in GB."""
    mem = psutil.virtual_memory()
    return mem.available / (1024 ** 3)

# Check GPU availability
has_gpu = False
try:
    import torch
    has_gpu = torch.cuda.is_available() or torch.backends.mps.is_available()
except ImportError:
    pass

# Set configuration based on memory
available_gb = get_available_ram_gb()

if not has_gpu:
    FAST_MODE = True
    MAX_TOKENS = 8192
else:
    if available_gb < 4:
        FAST_MODE = True
        MAX_TOKENS = 8192
    elif available_gb < 8:
        MAX_TOKENS = 16384
    elif available_gb > 32:
        MAX_TOKENS = 0
        FULL_FEATURE_MODE = True

DISABLE_VISUAL_ANALYSIS = os.environ.get("DOCSRAY_DISABLE_VISUALS", "0") == "1"
# export DOCSRAY_DISABLE_VISUALS=1
# docsray process document.pdf