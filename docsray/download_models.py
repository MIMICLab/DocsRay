#!/usr/bin/env python3
"""Model download script for DocsRay"""

import os
import sys
import urllib.request
from docsray.config import MODEL_DIR, FAST_MODE, STANDARD_MODE, FULL_FEATURE_MODE
from docsray.config import ALL_MODELS, FAST_MODELS, STANDARD_MODELS, FULL_FEATURE_MODELS
from docsray.config import MODEL_TYPE_TO_SIZE

def get_models_for_download(model_type=None):
    """Get models to download based on model type and system mode"""
    # Include embedding models based on system mode
    if FAST_MODE:
        embedding_models = [m for m in FAST_MODELS if "bge-m3" in m["file"] or "multilingual-e5" in m["file"]]
    elif STANDARD_MODE:
        embedding_models = [m for m in STANDARD_MODELS if "bge-m3" in m["file"] or "multilingual-e5" in m["file"]]
    elif FULL_FEATURE_MODE:
        embedding_models = [m for m in FULL_FEATURE_MODELS if "bge-m3" in m["file"] or "multilingual-e5" in m["file"]]
    else:
        # Default to FAST mode embedding models
        embedding_models = [m for m in FAST_MODELS if "bge-m3" in m["file"] or "multilingual-e5" in m["file"]]
    
    # Get LLM models for the specified type
    if model_type:
        model_size = MODEL_TYPE_TO_SIZE.get(model_type, "4b")
        llm_models = [m for m in ALL_MODELS if f"gemma-3-{model_size}-it" in m["file"]]
    else:
        # If no specific type, use system mode selection
        if FAST_MODE:
            llm_models = [m for m in FAST_MODELS if "gemma" in m["file"]]
        elif STANDARD_MODE:
            llm_models = [m for m in STANDARD_MODELS if "gemma" in m["file"]]
        elif FULL_FEATURE_MODE:
            llm_models = [m for m in FULL_FEATURE_MODELS if "gemma" in m["file"]]
        else:
            llm_models = [m for m in ALL_MODELS if "gemma-3-4b-it" in m["file"]]  # Default to 4b
    
    # Filter LLM models based on system mode for quantization level
    filtered_llm_models = []
    for model in llm_models:
        if FAST_MODE and "FAST_MODE" in model["required"]:
            filtered_llm_models.append(model)
        elif STANDARD_MODE and "STANDARD_MODE" in model["required"]:
            filtered_llm_models.append(model)
        elif FULL_FEATURE_MODE and "FULL_FEATURE_MODE" in model["required"]:
            filtered_llm_models.append(model)
        elif not (FAST_MODE or STANDARD_MODE or FULL_FEATURE_MODE):
            # Default case - use fast mode models
            if "FAST_MODE" in model["required"]:
                filtered_llm_models.append(model)
    
    return embedding_models + filtered_llm_models

# Default models for backward compatibility
if FAST_MODE:
    models = FAST_MODELS
elif STANDARD_MODE:
    models = STANDARD_MODELS
elif FULL_FEATURE_MODE:
    models = FULL_FEATURE_MODELS
else:
    models = FAST_MODELS
    

def show_progress(block_num, block_size, total_size):
    """Display download progress"""
    if total_size > 0:
        downloaded = block_num * block_size
        percent = min((downloaded / total_size) * 100, 100)
        downloaded_mb = downloaded / (1024 * 1024)
        total_mb = total_size / (1024 * 1024)
        print(f"\rDownloading: {percent:.1f}% ({downloaded_mb:.1f}/{total_mb:.1f} MB)", 
              end="", flush=True)

def download_models(model_type=None, force=False):
    """Download required models to user's home directory"""
    
    # Get models to download
    if model_type:
        models_to_download = get_models_for_download(model_type)
        print(f"Starting DocsRay model download for {model_type} type...")
        model_size = MODEL_TYPE_TO_SIZE.get(model_type, "4b")
        print(f"Model size: {model_size} (gemma-3-{model_size}-it)")
    else:
        models_to_download = models
        print("Starting DocsRay model download...")
    
    print(f"Storage location: {MODEL_DIR}")
    print(f"Models to download: {len(models_to_download)}")
    
    for i, model in enumerate(models_to_download, 1):
        model_path = model["dir"] / model["file"]    
        print(f"\n[{i}/{len(models_to_download)}] Checking {model['file']}...")

        if model_path.exists() and not force:
            file_size = model_path.stat().st_size / (1024 * 1024)
            print(f"✅ Already exists ({file_size:.1f} MB)", file=sys.stderr)
            continue
        elif model_path.exists() and force:
            file_size = model_path.stat().st_size / (1024 * 1024)
            print(f"🔄 Force re-downloading ({file_size:.1f} MB)", file=sys.stderr)
        
        print(f"📥 Starting download: {model['file']}", file=sys.stderr)
        print(f"URL: {model['url']}", file=sys.stderr)
        
        # Create directory
        model["dir"].mkdir(parents=True, exist_ok=True)
        
        try:
            urllib.request.urlretrieve(
                model["url"], 
                str(model_path), 
                reporthook=show_progress
            )
            print(f"\n✅ Completed: {model['file']}", file=sys.stderr)
            
            # Check file size
            file_size = model_path.stat().st_size / (1024 * 1024)
            print(f"   File size: {file_size:.1f} MB")
            
        except Exception as e:
            print(f"\n❌ Failed: {model['file']}", file=sys.stderr)
            print(f"   Error: {e}", file=sys.stderr)
            
            # Remove failed file
            if model_path.exists():
                model_path.unlink()
            
            print(f"   Manual download URL: {model['url']}", file=sys.stderr)
            print(f"   Save to: {model_path}", file=sys.stderr)
            
            # Ask whether to continue
            response = input("   Continue downloading? (y/n): ")
            if response.lower() != 'y':
                print("Download cancelled.", file=sys.stderr)
                sys.exit(1)
    
    print("\n🎉 All model downloads completed!", file=sys.stderr)
    print("You can now use DocsRay!", file=sys.stderr)

def check_models(model_type=None):
    """Check the status of currently downloaded models"""
    
    # Get models to check
    if model_type:
        models_to_check = get_models_for_download(model_type)
        print(f"📋 Model Status Check for {model_type} type:", file=sys.stderr)
        model_size = MODEL_TYPE_TO_SIZE.get(model_type, "4b")
        print(f"Model size: {model_size} (gemma-3-{model_size}-it)", file=sys.stderr)
    else:
        models_to_check = models
        print("📋 Model Status Check:", file=sys.stderr)
    
    print(f"Base path: {MODEL_DIR}", file=sys.stderr)
    
    total_size = 0
    available_models = []
    missing_models = []
    
    for model in models_to_check:
        full_path = model["dir"] / model["file"]
        
        if full_path.exists():
            file_size = full_path.stat().st_size / (1024 * 1024)
            total_size += file_size
            available_models.append((model['file'], file_size))
        else:
            missing_models.append(model['file'])
    
    print("\n📊 Available Models:", file=sys.stderr)
    for desc, size in available_models:
        print(f"  ✅ {desc}: {size:.1f} MB", file=sys.stderr)
    
    if missing_models:
        print("\n❌ Missing Models:", file=sys.stderr)
        for desc in missing_models:
            print(f"  ❌ {desc}", file=sys.stderr)
    
    print("\n" + "="*50, file=sys.stderr)
    print(f"📈 Summary:", file=sys.stderr)
    if total_size > 0:
        gb_size = total_size / 1024
        print(f"  • Total size: {total_size:.1f} MB ({gb_size:.2f} GB)", file=sys.stderr)
    
    if missing_models:
        print(f"\n⚠️  {len(missing_models)} models are missing.", file=sys.stderr)
        print("💡 Run 'docsray download-models' to download them.", file=sys.stderr)
    else:
        print("\n✅ All models are ready for use!", file=sys.stderr)
    
    return {
        'available': len(available_models),
        'missing': len(missing_models),
        'total_size_mb': total_size
    }

def main():
    """Main entry point for command line"""
    import argparse
    
    parser = argparse.ArgumentParser(description="DocsRay Model Download Tool")
    parser.add_argument("--check", action="store_true", help="Check current model status only")
    parser.add_argument("--force", action="store_true", help="Force re-download existing models")
    
    args = parser.parse_args()
    
    if args.check:
        check_models()
    else:
        download_models(force=args.force)

if __name__ == "__main__":
    main()
