"""
Pandoc installation and setup utilities
"""
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


def ensure_pandoc():
    """Ensure pandoc is available"""
    if not setup_pandoc_path():
        # Try to install
        if not install_pandoc():
            return False
    return True