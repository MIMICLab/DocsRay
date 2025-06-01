"""
DocsRay - PDF Question-Answering System with MCP Integration
"""

__version__ = "1.0.2"
__author__ = "Taehoon Kim"

import os
import sys

# Suppress logs
os.environ["LLAMA_LOG_LEVEL"] = "40"
os.environ["GGML_LOG_LEVEL"] = "error"
os.environ["LLAMA_CPP_LOG_LEVEL"] = "ERROR"

# Import config
from .config import FAST_MODE, FULL_FEATURE_MODE, MAX_TOKENS, DOCSRAY_HOME, DATA_DIR, MODEL_DIR, CACHE_DIR

# Check if llama-cpp-python needs update (for post-install message)
def check_llama_cpp_python():
    """Check if llama-cpp-python needs the hotfix"""
    try:
        import llama_cpp
        # Check if this is the forked version by trying to import Gemma3ChatHandler
        try:
            from llama_cpp.llama_chat_format import Gemma3ChatHandler
            return True  # Hotfix already applied
        except ImportError:
            return False  # Need hotfix
    except ImportError:
        return None  # Not installed at all

# Display post-install message if needed
def display_hotfix_message():
    """Display hotfix message for Gemma3 support"""
    llama_status = check_llama_cpp_python()
    
    if llama_status is False:
        print("\n" + "="*70)
        print("🔧 DocsRay Post-Install Setup")
        print("="*70)
        print("\n# 1-1. Hotfix (Temporary)")
        print("# Hotfix: Use the forked version of llama-cpp-python for Gemma3 Support")
        print("# Note: This is a temporary fix until the official library supports Gemma3")
        print("# Install the forked version of llama-cpp-python")
        print("\npip install git+https://github.com/kossum/llama-cpp-python.git@main\n")
        print("="*70 + "\n")

# Check if this is being run after pip install (not during import in normal usage)
if os.environ.get('_DOCSRAY_SETUP_CHECK') != '1':
    # Set flag to prevent recursive checks
    os.environ['_DOCSRAY_SETUP_CHECK'] = '1'
    
    # Only show message if running from command line after install
    if hasattr(sys, 'ps1') or not sys.stderr.isatty():
        # Interactive mode or not a terminal - skip message
        pass
    elif any(arg in sys.argv for arg in ['install', 'develop', 'egg_info']):
        # During installation - skip message  
        pass
    else:
        # Likely first import after installation
        display_hotfix_message()

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