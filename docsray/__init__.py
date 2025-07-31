"""
DocsRay - Document Question-Answering System with MCP Integration
"""

__version__ = "1.8.0"
__author__ = "Taehoon Kim"

import os
import sys
from pathlib import Path

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

# Check if this is the first run after installation
def check_first_run():
    """Check if this is the first run and try automatic setup"""
    try:
        # Skip if running in a subprocess or non-interactive environment
        if not sys.stdout.isatty() or os.environ.get('DOCSRAY_SKIP_FIRST_RUN'):
            return
            
        # Check for first-run flag file
        first_run_flag = Path.home() / ".docsray" / ".first_run_complete"
        
        if not first_run_flag.exists():
            import subprocess
            
            print("\n🚀 First run detected. Attempting automatic setup...")
            print("-" * 60)
            
            setup_success = False
            models_success = False
            
            # Try to run setup
            try:
                print("\n1️⃣ Running dependency setup...")
                result = subprocess.run([sys.executable, '-m', 'docsray.auto_setup', '--force'], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    setup_success = True
                    print("✅ Dependencies installed successfully!")
                else:
                    print("⚠️  Dependency setup failed")
            except Exception as e:
                print(f"⚠️  Could not run automatic setup: {e}")
            
            # Try to download lite model
            try:
                print("\n2️⃣ Downloading lite model (~3GB)...")
                result = subprocess.run([sys.executable, '-m', 'docsray.download_models', '--model-type', 'lite'], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    models_success = True
                    print("✅ Model downloaded successfully!")
                else:
                    print("⚠️  Model download failed")
            except Exception as e:
                print(f"⚠️  Could not download models: {e}")
            
            print("-" * 60)
            
            # Show appropriate message based on results
            if setup_success and models_success:
                print("\n✅ Automatic setup completed successfully!")
                print("\nDocsRay is ready to use with the lite model.")
                print("\nFor other model sizes, use:")
                print("  docsray download-models --model-type base   # 12b model (~8GB)")
                print("  docsray download-models --model-type pro    # 27b model (~16GB)")
            else:
                # Show simple instructions if automatic setup failed
                from .post_install import show_post_install_message
                show_post_install_message()
            
            # Create flag file to prevent showing again
            first_run_flag.parent.mkdir(parents=True, exist_ok=True)
            first_run_flag.touch()
            
            print("\n")
    except Exception:
        # Silently fail if there's any issue
        pass

# Check on import but only in main process
if __name__ != "__main__" and "docsray" in sys.argv[0]:
    check_first_run()

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
