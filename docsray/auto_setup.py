#!/usr/bin/env python3
"""Automatic setup script for DocsRay dependencies"""

import os
import sys
import platform
import subprocess
import shutil
from pathlib import Path

def is_root():
    """Check if running as root user"""
    return os.geteuid() == 0

def has_sudo_privileges():
    """Check if user can use sudo without password or is root"""
    # Check if running as root
    if os.geteuid() == 0:
        return True
    
    # Check if sudo is available and user can use it
    if shutil.which('sudo'):
        try:
            # Test sudo with a harmless command
            result = subprocess.run(['sudo', '-n', 'true'], 
                                  capture_output=True, stderr=subprocess.DEVNULL)
            return result.returncode == 0
        except:
            pass
    
    return False

def run_command(cmd, check=True):
    """Run a command with or without sudo based on environment"""
    # As root, don't use sudo
    if is_root():
        # Remove 'sudo' from command if present
        if cmd[0] == 'sudo':
            cmd = cmd[1:]
    elif not has_sudo_privileges() and cmd[0] == 'sudo':
        # If sudo is needed but not available, try without it
        print("⚠️  Running without sudo privileges...")
        cmd = cmd[1:]
    
    return subprocess.run(cmd, check=check)

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
    
    # Check for Apple Silicon (MPS/Metal)
    if platform.system() == "Darwin":
        # Check if it's ARM-based Mac (Apple Silicon)
        try:
            result = subprocess.run(['sysctl', '-n', 'hw.optional.arm64'], capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip() == "1":
                return "metal"
        except:
            # Fallback check
            if platform.processor() == "arm" or platform.machine() == "arm64":
                return "metal"
    
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
                run_command(['brew', 'install', 'ffmpeg'])
                return True
            else:
                print("❌ Homebrew not found. Please install Homebrew first:")
                print("   /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"")
                return False
                
        elif system == "Linux":
            if shutil.which('apt-get'):
                print("Using apt to install ffmpeg...")
                run_command(['sudo', 'apt', 'update'])
                run_command(['sudo', 'apt', 'install', '-y', 'ffmpeg'])
                return True
            elif shutil.which('yum'):
                print("Using yum to install ffmpeg...")
                run_command(['sudo', 'yum', 'install', '-y', 'ffmpeg'])
                return True
            elif shutil.which('dnf'):
                print("Using dnf to install ffmpeg...")
                run_command(['sudo', 'dnf', 'install', '-y', 'ffmpeg'])
                return True
            elif shutil.which('pacman'):
                print("Using pacman to install ffmpeg...")
                run_command(['sudo', 'pacman', '-S', '--noconfirm', 'ffmpeg'])
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

def get_cuda_version():
    """Detect installed CUDA version"""
    try:
        # Try nvidia-smi first
        result = subprocess.run(['nvidia-smi'], capture_output=True, text=True)
        if result.returncode == 0:
            # Parse CUDA version from nvidia-smi output
            for line in result.stdout.split('\n'):
                if 'CUDA Version:' in line:
                    # Extract version like "12.1" from "CUDA Version: 12.1"
                    version = line.split('CUDA Version:')[1].strip().split()[0]
                    major, minor = version.split('.')[:2]
                    return f"{major}.{minor}"
    except:
        pass
    
    # Try nvcc
    try:
        result = subprocess.run(['nvcc', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            # Parse version from nvcc output
            for line in result.stdout.split('\n'):
                if 'release' in line:
                    # Extract version like "12.1" from "Cuda compilation tools, release 12.1"
                    parts = line.split('release')[1].strip().split(',')[0].strip()
                    major, minor = parts.split('.')[:2]
                    return f"{major}.{minor}"
    except:
        pass
    
    return None

def setup_llama_cpp():
    """Install appropriate llama-cpp-python wheel based on platform"""
    gpu_type = get_gpu_type()
    
    if gpu_type == "cuda":
        return setup_cuda_llama_cpp()
    elif gpu_type == "metal":
        return setup_metal_llama_cpp()
    else:
        return setup_cpu_llama_cpp()

def setup_cpu_llama_cpp():
    """Install CPU-optimized llama-cpp-python"""
    print("💻 Installing CPU-optimized llama-cpp-python...")
    
    try:
        subprocess.run([
            sys.executable, '-m', 'pip', 'install', 
            'llama-cpp-python==0.3.9',
            '--extra-index-url', 'https://abetlen.github.io/llama-cpp-python/whl/cpu',
            '--upgrade', '--force-reinstall', '--no-cache-dir'
        ], check=True)
        
        print("✅ Successfully installed CPU-optimized llama-cpp-python!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install CPU llama-cpp-python: {e}")
        return False

def setup_metal_llama_cpp():
    """Install Metal-accelerated llama-cpp-python for Apple Silicon"""
    print("🍎 Installing Metal-accelerated llama-cpp-python for Apple Silicon...")
    
    try:
        subprocess.run([
            sys.executable, '-m', 'pip', 'install', 
            'llama-cpp-python==0.3.9',
            '--extra-index-url', 'https://abetlen.github.io/llama-cpp-python/whl/metal',
            '--upgrade', '--force-reinstall', '--no-cache-dir'
        ], check=True)
        
        print("✅ Successfully installed Metal-accelerated llama-cpp-python!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install Metal llama-cpp-python: {e}")
        return False

def setup_cuda_llama_cpp():
    """Install llama-cpp-python with CUDA support using pre-built wheels"""
    print("🚀 Installing llama-cpp-python with CUDA support...")
    
    # Detect CUDA version
    cuda_version = get_cuda_version()
    if not cuda_version:
        print("⚠️  Could not detect CUDA version, falling back to source build")
        return setup_cuda_llama_cpp_from_source()
    
    print(f"🔍 Detected CUDA version: {cuda_version}")
    
    # Map CUDA version to wheel index
    cuda_wheel_map = {
        "12.1": "cu121",
        "12.2": "cu122",
        "12.3": "cu123",
        "12.4": "cu124",
        "12.5": "cu125",
        "11.7": "cu117",
        "11.8": "cu118",
    }
    
    cuda_tag = cuda_wheel_map.get(cuda_version)
    if not cuda_tag:
        print(f"⚠️  No pre-built wheel for CUDA {cuda_version}, trying closest version...")
        # Try to find closest version
        if cuda_version.startswith("12."):
            cuda_tag = "cu121"  # Use oldest 12.x wheel
        elif cuda_version.startswith("11."):
            cuda_tag = "cu118"  # Use newest 11.x wheel
        else:
            print("⚠️  Unsupported CUDA version, falling back to source build")
            return setup_cuda_llama_cpp_from_source()
    
    try:
        # Use pre-built CUDA wheel
        print(f"📦 Using pre-built wheel for CUDA {cuda_tag}")
        subprocess.run([
            sys.executable, '-m', 'pip', 'install', 
            'llama-cpp-python==0.3.9',
            '--extra-index-url', f'https://abetlen.github.io/llama-cpp-python/whl/{cuda_tag}',
            '--upgrade', '--force-reinstall', '--no-cache-dir'
        ], check=True)
        
        print("✅ Successfully installed CUDA-enabled llama-cpp-python from pre-built wheel!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install from pre-built wheel: {e}")
        print("Falling back to source build...")
        return setup_cuda_llama_cpp_from_source()

def setup_cuda_llama_cpp_from_source():
    """Install llama-cpp-python with CUDA support from source"""
    print("🔧 Building llama-cpp-python from source with CUDA support...")
    
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
        print(f"❌ Failed to build CUDA-enabled llama-cpp-python from source: {e}")
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
    if is_root():
        print(f"   Running as: root")
    
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
    
    # 2. Setup llama-cpp-python with appropriate acceleration
    print(f"\n🔧 Installing llama-cpp-python for {gpu_type.upper()} acceleration...")
    
    # Always install llama-cpp-python (it's required and not in requirements.txt)
    if setup_llama_cpp():
        print(f"✅ {gpu_type.upper()}-optimized llama-cpp-python installed successfully!")
    else:
        print(f"⚠️  Failed to install optimized llama-cpp-python")
        print("   Please install manually: pip install llama-cpp-python==0.3.9")
        setup_needed = True
    
    # 3. Additional recommendations for macOS and Windows
    system = platform.system()
    if system in ["Darwin", "Windows"]:
        print("\n📚 Additional Recommendations:")
        print("\n1. LibreOffice for better Office document support:")
        if system == "Darwin":
            print("   brew install libreoffice")
        else:  # Windows
            print("   Download from: https://www.libreoffice.org/download/")
        
        print("\n2. For HWP/HWPX support, install h2orestart extension:")
        print("   https://extensions.libreoffice.org/en/extensions/show/27504")
        print("\n3. For document conversions, install pandoc:")
        if system == "Darwin":
            print("   brew install pandoc")
        else:  # Windows
            print("   Download from: https://pandoc.org/installing.html")
    
    if not setup_needed:
        print("\n✅ All automatic dependencies are properly installed!")
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