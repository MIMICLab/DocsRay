"""
DocsRay - PDF Question-Answering System with MCP Integration
"""

__version__ = "0.1.1"
__author__ = "Taehoon Kim"

import os
from pathlib import Path

# Set up default paths
DOCSRAY_HOME = Path(os.environ.get("DOCSRAY_HOME", Path.home() / ".docsray"))
DATA_DIR = DOCSRAY_HOME / "data"
MODEL_DIR = DOCSRAY_HOME / "models"
CACHE_DIR = DOCSRAY_HOME / "cache"

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