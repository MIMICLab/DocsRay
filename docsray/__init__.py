"""
DocsRay - PDF Question-Answering System with MCP Integration
"""

__version__ = "1.0.0"
__author__ = "Taehoon Kim"

import os
from pathlib import Path

# Suppress logs
os.environ["LLAMA_LOG_LEVEL"] = "40"
os.environ["GGML_LOG_LEVEL"] = "error"
os.environ["LLAMA_CPP_LOG_LEVEL"] = "ERROR"

# Paths
DOCSRAY_HOME = Path(os.environ.get("DOCSRAY_HOME", Path.home() / ".docsray"))
DATA_DIR = DOCSRAY_HOME / "data"
MODEL_DIR = DOCSRAY_HOME / "models"
CACHE_DIR = DOCSRAY_HOME / "cache"

# Create directories
for dir_path in [DOCSRAY_HOME, DATA_DIR, MODEL_DIR, CACHE_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

# Import config
from .config import FAST_MODE, FULL_FEATURE_MODE, MAX_TOKENS

__all__ = [
    "__version__", 
    "DOCSRAY_HOME", 
    "DATA_DIR", 
    "MODEL_DIR", 
    "CACHE_DIR",
    "FAST_MODE",
    "FULL_FEATURE_MODE", 
    "MAX_TOKENS"
]