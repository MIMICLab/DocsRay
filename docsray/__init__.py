"""
DocsRay - Document Question-Answering System with MCP Integration
"""

__version__ = "1.6.1"
__author__ = "Taehoon Kim"

import os
import sys

# Suppress logs if not already set
if "LLAMA_LOG_LEVEL" not in os.environ:
    os.environ["LLAMA_LOG_LEVEL"] = "40"
if "GGML_LOG_LEVEL" not in os.environ:
    os.environ["GGML_LOG_LEVEL"] = "error"
if "LLAMA_CPP_LOG_LEVEL" not in os.environ:
    os.environ["LLAMA_CPP_LOG_LEVEL"] = "ERROR"

# Import config
from .config import FAST_MODE, STANDARD_MODE, FULL_FEATURE_MODE
from .config import FAST_MODELS, STANDARD_MODELS, FULL_FEATURE_MODELS, ALL_MODELS
from .config import MAX_TOKENS, DOCSRAY_HOME, DATA_DIR, MODEL_DIR, CACHE_DIR, USE_TESSERACT

__all__ = [
    "__version__", 
    "DOCSRAY_HOME", 
    "DATA_DIR", 
    "MODEL_DIR", 
    "CACHE_DIR",
    "FAST_MODE",
    "STANDARD_MODE",
    "FULL_FEATURE_MODE", 
    "FAST_MODELS",
    "STANDARD_MODELS",
    "FULL_FEATURE_MODELS",
    "ALL_MODELS",
    "USE_TESSERACT",
    "MAX_TOKENS"
]
