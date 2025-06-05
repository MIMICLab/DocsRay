#!/usr/bin/env python3
"""Model download script for DocsRay"""

import os
import sys
import urllib.request
from docsray.config import MODEL_DIR, FAST_MODE, STANDARD_MODE, FULL_FEATURE_MODE
from docsray.config import ALL_MODELS, FAST_MODELS, STANDARD_MODELS, FULL_FEATURE_MODELS

if FAST_MODE:
    models = FAST_MODELS
elif STANDARD_MODE:
    models = STANDARD_MODELS
elif FULL_FEATURE_MODE:
    models = FULL_FEATURE_MODELS
    

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

    print("Starting DocsRay model download...")
    print(f"Storage location: {MODEL_DIR}")
    
    for i, model in enumerate(models, 1):
        model_path = model["dir"] / model["file"]    
        print(f"\n[{i}/{len(models)}] Checking {model['file']}...")

        if model_path.exists():
            file_size = model_path.stat().st_size / (1024 * 1024)
            print(f"✅ Already exists ({file_size:.1f} MB)", file=sys.stderr)
            continue
        
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

def check_models():
    """Check the status of currently downloaded models"""
    
    print("📋 Model Status Check:", file=sys.stderr)
    print(f"Base path: {MODEL_DIR}", file=sys.stderr)
    
    total_size = 0
    available_models = []
    missing_models = []
    
    for model in models:
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
    
    args = parser.parse_args()
    
    if args.check:
        check_models()
    else:
        download_models()

if __name__ == "__main__":
    main()
