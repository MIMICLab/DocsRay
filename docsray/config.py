import os
import torch
import psutil
from pathlib import Path
import sys
# Paths
DOCSRAY_HOME = Path(os.environ.get("DOCSRAY_HOME", Path.home() / ".docsray"))
DATA_DIR = DOCSRAY_HOME / "data"
MODEL_DIR = DOCSRAY_HOME / "models"
CACHE_DIR = DOCSRAY_HOME / "cache"

import os
import sys
import platform
import subprocess
import pypandoc
from pathlib import Path


def check_pandoc_installed():
    """Check if pandoc is installed on the system"""
    try:
        # Check via pypandoc
        pypandoc.get_pandoc_version()
        return True
    except:
        # Check via system command
        try:
            subprocess.run(['pandoc', '--version'], 
                         capture_output=True, 
                         check=True)
            return True
        except:
            return False


def install_pandoc():
    """Install pandoc based on platform"""
    system = platform.system().lower()
    
    if check_pandoc_installed():
        print("pandoc is already installed.")
        return True
    
    print(f"Installing pandoc... (Platform: {system})")
    
    try:
        # Try automatic installation via pypandoc
        # Install in user's home directory under .pandoc
        home_dir = Path.home()
        pandoc_dir = home_dir / ".pandoc"
        pandoc_dir.mkdir(exist_ok=True)
        
        # Set platform-specific download location
        if system == "windows":
            # Windows installs in AppData
            pandoc_dir = Path(os.environ.get('APPDATA', home_dir)) / "pandoc"
            pandoc_dir.mkdir(exist_ok=True)
        
        pypandoc.download_pandoc(targetfolder=str(pandoc_dir))
        
        # Add pandoc path to environment variable
        if system == "windows":
            os.environ['PATH'] = f"{pandoc_dir};{os.environ['PATH']}"
        else:
            os.environ['PATH'] = f"{pandoc_dir}:{os.environ['PATH']}"
        
        print(f"pandoc has been installed to {pandoc_dir}", file=sys.stderr)
        return True
        
    except Exception as e:
        print(f"Automatic installation failed: {e}", file=sys.stderr)
        print("\nManual installation instructions:", file=sys.stderr)
        
        if system == "darwin":  # macOS
            print("macOS:", file=sys.stderr)
            print("  brew install pandoc", file=sys.stderr)
            print("or", file=sys.stderr)
            print("  sudo port install pandoc", file=sys.stderr)
            
        elif system == "linux":
            print("Ubuntu/Debian:", file=sys.stderr)
            print("  sudo apt-get update && sudo apt-get install pandoc", file=sys.stderr)
            print("\nFedora/RedHat/CentOS:", file=sys.stderr)
            print("  sudo dnf install pandoc", file=sys.stderr)
            print("\nArch Linux:", file=sys.stderr)
            print("  sudo pacman -S pandoc", file=sys.stderr)
            
        elif system == "windows":
            print("Windows:", file=sys.stderr)
            print("  1. Using Chocolatey: choco install pandoc", file=sys.stderr)
            print("  2. Using Scoop: scoop install pandoc", file=sys.stderr)
            print("  3. Or download directly from https://pandoc.org/installing.html", file=sys.stderr)
        
        print("\nPlease install pandoc and run the script again.", file=sys.stderr)
        return False


def setup_pandoc_path():
    """Setup pandoc path"""
    system = platform.system().lower()
    
    # Check if already in PATH
    if check_pandoc_installed():
        return True
    
    # Check common installation locations
    common_paths = []
    
    if system == "darwin":  # macOS
        common_paths = [
            "/usr/local/bin/pandoc",
            "/opt/homebrew/bin/pandoc",
            "/opt/local/bin/pandoc",
            str(Path.home() / ".pandoc" / "pandoc")
        ]
    elif system == "linux":
        common_paths = [
            "/usr/bin/pandoc",
            "/usr/local/bin/pandoc",
            str(Path.home() / ".pandoc" / "pandoc"),
            str(Path.home() / ".local" / "bin" / "pandoc")
        ]
    elif system == "windows":
        common_paths = [
            r"C:\Program Files\Pandoc\pandoc.exe",
            r"C:\Program Files (x86)\Pandoc\pandoc.exe",
            str(Path(os.environ.get('APPDATA', '')) / "pandoc" / "pandoc.exe"),
            str(Path.home() / ".pandoc" / "pandoc.exe")
        ]
    
    # Set found pandoc path
    for path in common_paths:
        if os.path.exists(path):
            # Tell pypandoc about the path
            os.environ['PYPANDOC_PANDOC'] = path
            print(f"Pandoc path set to: {path}", file=sys.stderr)
            return True
    
    return False

if not setup_pandoc_path():
    # Try to install
    if not install_pandoc():
        sys.exit(1)
try:
    import pytesseract
    USE_TESSERACT =True
except:
    print("Pytesseract not installed. Using gemma3 for OCR", file=sys.stderr)
    USE_TESSERACT = False

# Create directories
for dir_path in [DOCSRAY_HOME, DATA_DIR, MODEL_DIR, CACHE_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

def get_available_ram_gb():
    mem = psutil.virtual_memory()
    return mem.available / (1024 ** 3)

def get_device_memory_gb():
    try:
        if torch.cuda.is_available():
            gpu_properties = torch.cuda.get_device_properties(0)
            total_memory = gpu_properties.total_memory / (1024**3)
            allocated_memory = torch.cuda.memory_allocated(0) / (1024**3)
            available_memory = total_memory - allocated_memory
            return available_memory, 'cuda'
        elif torch.backends.mps.is_available():
            available_memory = get_available_ram_gb()
            return available_memory * 0.8, 'mps'  
        else:
            # CPU only
            return get_available_ram_gb(), 'cpu'
    except Exception as e:
        print(e)
        return get_available_ram_gb(), 'cpu'


has_gpu = torch.cuda.is_available() or torch.backends.mps.is_available()
device_type = 'cpu'

available_gb, device_type = get_device_memory_gb()


FAST_MODE = False
MAX_TOKENS = 32768
STANDARD_MODE = False
FULL_FEATURE_MODE = False
min_available_gb = 8

if not has_gpu:
    FAST_MODE = True
    DISABLE_VISUAL_ANALYSIS = True
    MAX_TOKENS = MAX_TOKENS // 4
else:
    if available_gb < min_available_gb * 2:
        FAST_MODE = True
        MAX_TOKENS = MAX_TOKENS // 4
    elif available_gb < min_available_gb * 3:
        STANDARD_MODE = True
        MAX_TOKENS = MAX_TOKENS // 2         
    else:
        FULL_FEATURE_MODE = True

FAST_MODELS = []
STANDARD_MODELS = []
FULL_FEATURE_MODELS = []

ALL_MODELS = [
    {
        "dir": MODEL_DIR / "bge-m3-gguf",
        "file": "bge-m3-Q8_0.gguf",
        "url": "https://huggingface.co/tgisaturday/Docsray/resolve/main/bge-m3-gguf/bge-m3-Q8_0.gguf",
        "required": ["FAST_MODE", "STANDARD_MODE"]
    },
{
        "dir": MODEL_DIR / "bge-m3-gguf",
        "file": "bge-m3-F16.gguf",
        "url": "https://huggingface.co/tgisaturday/Docsray/resolve/main/bge-m3-gguf/bge-m3-F16.gguf",
        "required": ["FULL_FEATURE_MODE"]
    },
    {
        "dir": MODEL_DIR / "multilingual-e5-large-gguf",
        "file": "multilingual-e5-large-Q8_0.gguf",
        "url": "https://huggingface.co/tgisaturday/Docsray/resolve/main/multilingual-e5-large-gguf/multilingual-e5-large-Q8_0.gguf",
        "required": ["FAST_MODE", "STANDARD_MODE"]
    },
    {
        "dir": MODEL_DIR / "multilingual-e5-large-gguf",
        "file": "multilingual-e5-large-F16.gguf",
        "url": "https://huggingface.co/tgisaturday/Docsray/resolve/main/multilingual-e5-large-gguf/multilingual-e5-large-F16.gguf",
        "required": ["FULL_FEATURE_MODE"]
    },
    {
        "dir": MODEL_DIR / "gemma-3-1b-it-GGUF",
        "file": "gemma-3-1b-it-Q4_K_M.gguf",
        "url": "https://huggingface.co/tgisaturday/Docsray/resolve/main/gemma-3-1b-it-GGUF/gemma-3-1b-it-Q4_K_M.gguf",
        "required": ["FAST_MODE"]
    },
    {
        "dir": MODEL_DIR / "gemma-3-1b-it-GGUF",
        "file": "gemma-3-1b-it-Q8_0.gguf",
        "url": "https://huggingface.co/tgisaturday/Docsray/resolve/main/gemma-3-1b-it-GGUF/gemma-3-1b-it-Q8_0.gguf",
        "required": ["STANDARD_MODE"]
    },
    {
        "dir": MODEL_DIR / "gemma-3-1b-it-GGUF",
        "file": "gemma-3-1b-it-F16.gguf",
        "url": "https://huggingface.co/tgisaturday/Docsray/resolve/main/gemma-3-1b-it-GGUF/gemma-3-1b-it-F16.gguf",
        "required": ["FULL_FEATURE_MODE"]
    },
    {
        "dir": MODEL_DIR / "gemma-3-4b-it-GGUF",
        "file": "gemma-3-4b-it-Q4_K_M.gguf",
        "url": "https://huggingface.co/tgisaturday/Docsray/resolve/main/gemma-3-4b-it-GGUF/gemma-3-4b-it-Q4_K_M.gguf",
        "required": ["FAST_MODE"]
    },
    {
        "dir": MODEL_DIR / "gemma-3-4b-it-GGUF",
        "file": "gemma-3-4b-it-Q8_0.gguf",
        "url": "https://huggingface.co/tgisaturday/Docsray/resolve/main/gemma-3-4b-it-GGUF/gemma-3-4b-it-Q8_0.gguf",
        "required": ["STANDARD_MODE"]
    },
    {
        "dir": MODEL_DIR / "gemma-3-4b-it-GGUF",
        "file": "gemma-3-4b-it-F16.gguf",
        "url": "https://huggingface.co/tgisaturday/Docsray/resolve/main/gemma-3-4b-it-GGUF/gemma-3-4b-it-F16.gguf",
        "required": ["FULL_FEATURE_MODE"]
    },
    {
        "dir": MODEL_DIR / "gemma-3-4b-it-GGUF",
        "file": "mmproj-gemma-3-4b-it-F16.gguf",
        "url": "https://huggingface.co/tgisaturday/Docsray/resolve/main/gemma-3-4b-it-GGUF/mmproj-gemma-3-4b-it-F16.gguf",
        "required": ["FAST_MODE", "STANDARD_MODE", "FULL_FEATURE_MODE"]
    }
]

for model in ALL_MODELS:
    if "FAST_MODE" in model["required"]:
        FAST_MODELS.append(model)
    if "STANDARD_MODE" in model["required"]:
        STANDARD_MODELS.append(model)
    if "FULL_FEATURE_MODE" in model["required"]:
        FULL_FEATURE_MODELS.append(model)

DISABLE_VISUAL_ANALYSIS = os.environ.get("DOCSRAY_DISABLE_VISUALS", "0") == "1"


if os.environ.get("DOCSRAY_DEBUG", "0") == "1":
    print(f"Current Device: {device_type}")
    print(f"Available Memory: {available_gb:.2f} GB")
    print(f"FAST_MODE: {FAST_MODE}")
    print(f"MAX_TOKENS: {MAX_TOKENS}")
    print(f"FULL_FEATURE_MODE: {FULL_FEATURE_MODE}")
