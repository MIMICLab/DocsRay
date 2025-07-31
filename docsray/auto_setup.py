#!/usr/bin/env python3
"""Automatic setup script for DocsRay dependencies"""

import os
import sys
import platform
import subprocess
import shutil
from pathlib import Path

def get_gpu_type():
    """Detect GPU type (CUDA, MPS, or CPU)"""
    # Check for NVIDIA GPU (CUDA)
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except ImportError:
        pass
    
    # Check nvidia-smi command
    try:
        result = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
        if result.returncode == 0:
            return "cuda"
    except FileNotFoundError:
        pass
    
    # Check for Apple Silicon (MPS)
    if platform.system() == "Darwin" and platform.processor() == "arm":
        return "mps"
    
    return "cpu"

def check_ffmpeg():
    """Check if ffmpeg is installed"""
    return shutil.which('ffmpeg') is not None

def install_ffmpeg():
    """Install ffmpeg based on the operating system"""
    system = platform.system()
    
    print("🎬 Installing ffmpeg for audio/video support...")
    
    try:
        if system == "Darwin":  # macOS
            if shutil.which('brew'):
                print("Using Homebrew to install ffmpeg...")
                subprocess.run(['brew', 'install', 'ffmpeg'], check=True)
                return True
            else:
                print("❌ Homebrew not found. Please install Homebrew first:")
                print("   /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
                return False
                
        elif system == "Linux":
            if shutil.which('apt-get'):
                print("Using apt to install ffmpeg...")
                subprocess.run(['sudo', 'apt', 'update'], check=True)
                subprocess.run(['sudo', 'apt', 'install', '-y', 'ffmpeg'], check=True)
                return True
            elif shutil.which('yum'):
                print("Using yum to install ffmpeg...")
                subprocess.run(['sudo', 'yum', 'install', '-y', 'ffmpeg'], check=True)
                return True
            elif shutil.which('dnf'):
                print("Using dnf to install ffmpeg...")
                subprocess.run(['sudo', 'dnf', 'install', '-y', 'ffmpeg'], check=True)
                return True
            elif shutil.which('pacman'):
                print("Using pacman to install ffmpeg...")
                subprocess.run(['sudo', 'pacman', '-S', '--noconfirm', 'ffmpeg'], check=True)
                return True
            else:
                print("❌ No supported package manager found")
                return False
                
        elif system == "Windows":
            print("❌ Automatic ffmpeg installation not supported on Windows")
            print("Please download from: https://ffmpeg.org/download.html")
            print("Or use: winget install ffmpeg (if you have Windows Package Manager)")
            return False
            
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install ffmpeg: {e}")
        return False
    except Exception as e:
        print(f"❌ Error during ffmpeg installation: {e}")
        return False
    
    return False

def setup_cuda_llama_cpp():
    """Install llama-cpp-python with CUDA support"""
    print("🚀 Installing llama-cpp-python with CUDA support...")
    
    try:
        env = os.environ.copy()
        env['CMAKE_ARGS'] = '-DGGML_CUDA=on'
        
        subprocess.run([
            sys.executable, '-m', 'pip', 'install', 
            'llama-cpp-python==0.3.9',
            '--upgrade', '--force-reinstall', '--no-cache-dir'
        ], env=env, check=True)
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install CUDA-enabled llama-cpp-python: {e}")
        return False

def check_dependencies():
    """Check all dependencies and return status"""
    status = {
        'ffmpeg': check_ffmpeg(),
        'gpu_type': get_gpu_type(),
        'cuda_llama_cpp': False
    }
    
    # Check if CUDA-enabled llama-cpp-python is needed and installed
    if status['gpu_type'] == 'cuda':
        try:
            import llama_cpp
            # Simple check - if it imports without error, assume it's working
            status['cuda_llama_cpp'] = True
        except ImportError:
            status['cuda_llama_cpp'] = False
    else:
        status['cuda_llama_cpp'] = True  # Not needed for non-CUDA systems
    
    return status

def run_setup(force=False):
    """Run the automatic setup process"""
    print("\n" + "="*60)
    print("🔧 DocsRay Automatic Setup")
    print("="*60)
    
    # Check current status
    status = check_dependencies()
    gpu_type = status['gpu_type']
    
    print(f"\n📊 System Information:")
    print(f"   OS: {platform.system()} {platform.release()}")
    print(f"   Python: {sys.version.split()[0]}")
    print(f"   GPU Type: {gpu_type.upper()}")
    
    setup_needed = False
    
    # 1. Check and install ffmpeg
    if not status['ffmpeg']:
        print("\n⚠️  ffmpeg is not installed (required for audio/video processing)")
        if force or input("Install ffmpeg automatically? (y/N): ").lower() == 'y':
            if install_ffmpeg():
                print("✅ ffmpeg installed successfully!")
            else:
                print("⚠️  Please install ffmpeg manually")
                setup_needed = True
    else:
        print("\n✅ ffmpeg is already installed")
    
    # 2. Setup CUDA if needed
    if gpu_type == 'cuda' and not status['cuda_llama_cpp']:
        print("\n🎮 NVIDIA GPU detected - CUDA acceleration available")
        if force or input("Install CUDA-enabled llama-cpp-python? (y/N): ").lower() == 'y':
            if setup_cuda_llama_cpp():
                print("✅ CUDA support installed successfully!")
            else:
                print("⚠️  CUDA setup failed, will use CPU mode")
                setup_needed = True
    elif gpu_type == 'cuda':
        print("\n✅ CUDA-enabled llama-cpp-python is already installed")
    elif gpu_type == 'mps':
        print("\n✅ Apple Silicon detected - MPS acceleration will be used")
    else:
        print("\n✅ CPU mode - No GPU acceleration setup needed")
    
    if not setup_needed:
        print("\n✅ All dependencies are properly installed!")
        return True
    else:
        print("\n⚠️  Some dependencies could not be installed automatically")
        print("   Please install them manually following the instructions above")
        return False

def main():
    """Main entry point for setup command"""
    import argparse
    
    parser = argparse.ArgumentParser(description="DocsRay automatic setup")
    parser.add_argument("--check", action="store_true", help="Check dependencies only")
    parser.add_argument("--force", action="store_true", help="Force installation without prompts")
    
    args = parser.parse_args()
    
    if args.check:
        # Check mode
        status = check_dependencies()
        all_good = all([
            status['ffmpeg'],
            status['cuda_llama_cpp'] or status['gpu_type'] != 'cuda'
        ])
        
        if all_good:
            print("✅ All dependencies are properly installed!")
            return 0
        else:
            print("\n⚠️  Missing dependencies detected:")
            if not status['ffmpeg']:
                print("   - ffmpeg (required for audio/video processing)")
            if status['gpu_type'] == 'cuda' and not status['cuda_llama_cpp']:
                print("   - CUDA-enabled llama-cpp-python")
            print("\nRun 'docsray setup' to install missing dependencies")
            return 1
    else:
        # Setup mode
        success = run_setup(force=args.force)
        return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())