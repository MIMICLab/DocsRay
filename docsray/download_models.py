#!/usr/bin/env python3
"""Model download script for DocsRay"""

import os
import sys
import urllib.request
from docsray.config import MODEL_DIR, FAST_MODE, STANDARD_MODE, FULL_FEATURE_MODE
from docsray.config import ALL_MODELS, FAST_MODELS, STANDARD_MODELS, FULL_FEATURE_MODELS

models = ALL_MODELS

def show_progress(block_num, block_size, total_size):
    """Display download progress"""
    if total_size > 0:
        downloaded = block_num * block_size
        percent = min((downloaded / total_size) * 100, 100)
        downloaded_mb = downloaded / (1024 * 1024)
        total_mb = total_size / (1024 * 1024)
        print(f"\rDownloading: {percent:.1f}% ({downloaded_mb:.1f}/{total_mb:.1f} MB)", 
              end="", flush=True)

def download_models():
    """Download required models to user's home directory"""


    for model in models:
        if FAST_MODE in model["required"]:
            FAST_MODELS.append(model)
        if STANDARD_MODE in model["required"]:
            STANDARD_MODELS.append(model)
        if FULL_FEATURE_MODE in model["required"]:
            FULL_FEATURE_MODELS.append(model)

    print("Starting DocsRay model download...")
    print(f"Storage location: {MODEL_DIR}")
    
    for i, model in enumerate(models, 1):
        model_path = model["dir"] / model["file"]    
        print(f"\n[{i}/{len(models)}] Checking {model['file']}...")
        if FAST_MODE:
            if model["file"] not in FAST_MODELS:
                print(f"Skipping {model['file']} for FAST_MODE")
                continue
        elif STANDARD_MODE:
            if model["file"] not in STANDARD_MODELS:
                print(f"Skipping {model['file']} for STANDARD_MODE")
                continue
        else:
            if model["file"] not in FULL_FEATURE_MODELS:
                print(f"Skipping {model['file']} for FULL_FEATURE_MODE")
                continue

        if model_path.exists():
            file_size = model_path.stat().st_size / (1024 * 1024)
            print(f"✅ Already exists ({file_size:.1f} MB)")
            continue
        
        print(f"📥 Starting download: {model['file']}")
        print(f"URL: {model['url']}")
        
        # Create directory
        model["dir"].mkdir(parents=True, exist_ok=True)
        
        try:
            urllib.request.urlretrieve(
                model["url"], 
                str(model_path), 
                reporthook=show_progress
            )
            print(f"\n✅ Completed: {model['file']}")
            
            # Check file size
            file_size = model_path.stat().st_size / (1024 * 1024)
            print(f"   File size: {file_size:.1f} MB")
            
        except Exception as e:
            print(f"\n❌ Failed: {model['file']}")
            print(f"   Error: {e}")
            
            # Remove failed file
            if model_path.exists():
                model_path.unlink()
            
            print(f"   Manual download URL: {model['url']}")
            print(f"   Save to: {model_path}")
            
            # Ask whether to continue
            response = input("   Continue downloading? (y/n): ")
            if response.lower() != 'y':
                print("Download cancelled.")
                sys.exit(1)
    
    print("\n🎉 All model downloads completed!")
    print("You can now use DocsRay!")

def check_models():
    """Check the status of currently downloaded models"""
    
    print("📋 Model Status Check:")
    print(f"Base path: {MODEL_DIR}")
    
    total_size = 0
    missing_count = 0
    for model_path, description in models:
        if FAST_MODE:
            if model_path not in FAST_MODELS:
                print(f"Skipping {model_path} for FAST_MODE")
                continue
        elif STANDARD_MODE:
            if model_path not in STANDARD_MODELS:
                print(f"Skipping {model_path} for STANDARD_MODE")
                continue
        else:
            if model_path not in FULL_FEATURE_MODELS:
                print(f"Skipping {model_path} for FULL_FEATURE_MODE")
                continue
        print(f"Checking {description}...")
        full_path = MODEL_DIR / model_path

        if full_path.exists():
            file_size = full_path.stat().st_size / (1024 * 1024)
            total_size += file_size
            print(f"✅ {description}: {file_size:.1f} MB")
        else:
            print(f"❌ {description}: Missing")
            missing_count += 1
    
    if total_size > 0:
        print(f"\nTotal downloaded size: {total_size:.1f} MB ({total_size/1024:.1f} GB)")
    
    if missing_count > 0:
        print(f"\n⚠️  {missing_count} models are missing. Run 'docsray download-models' to download them.")
    else:
        print("\n✅ All models are ready!")

def main():
    """Main entry point for command line"""
    import argparse
    
    parser = argparse.ArgumentParser(description="DocsRay Model Download Tool")
    parser.add_argument("--check", action="store_true", help="Check current model status only")
    
    args = parser.parse_args()
    
    if args.check:
        check_models()
    else:
        download_models()

if __name__ == "__main__":
    main()