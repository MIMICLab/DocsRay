# docsray/__init__.py
"""
DocsRay - PDF Question-Answering System with MCP Integration
"""

__version__ = "0.1.0"
__author__ = "MIMIC LAB"

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

# Export main components
from .chatbot import PDFChatBot
from .mcp_server import Server as MCPServer

__all__ = ["PDFChatBot", "MCPServer", "__version__"]