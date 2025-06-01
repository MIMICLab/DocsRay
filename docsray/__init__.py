"""
DocsRay - PDF Question-Answering System with MCP Integration
"""

__version__ = "1.1.4"
__author__ = "Taehoon Kim"

import os
import sys

# Suppress logs
os.environ["LLAMA_LOG_LEVEL"] = "40"
os.environ["GGML_LOG_LEVEL"] = "error"
os.environ["LLAMA_CPP_LOG_LEVEL"] = "ERROR"

# Import config
from .config import FAST_MODE, FULL_FEATURE_MODE, MAX_TOKENS, DOCSRAY_HOME, DATA_DIR, MODEL_DIR, CACHE_DIR

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