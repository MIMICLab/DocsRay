#!/usr/bin/env python3
"""Post-installation script for DocsRay"""

import sys
import platform
import subprocess
import shutil
import os


def is_root():
    """Check if running as root user"""
    return os.geteuid() == 0

def check_ffmpeg():
    """Check if ffmpeg is installed"""
    return shutil.which('ffmpeg') is not None

def get_ffmpeg_install_command():
    """Get platform-specific ffmpeg installation command"""
    system = platform.system()
    if system == "Darwin":  # macOS
        return "brew install ffmpeg"
    elif system == "Linux":
        # Check for different package managers
        use_sudo = not is_root()
        sudo_prefix = "sudo " if use_sudo else ""
        
        if shutil.which('apt-get'):
            return f"{sudo_prefix}apt update && {sudo_prefix}apt install ffmpeg"
        elif shutil.which('yum'):
            return f"{sudo_prefix}yum install ffmpeg"
        elif shutil.which('dnf'):
            return f"{sudo_prefix}dnf install ffmpeg"
        elif shutil.which('pacman'):
            return f"{sudo_prefix}pacman -S ffmpeg"
        else:
            return "Please install ffmpeg using your system's package manager"
    elif system == "Windows":
        return """Please download ffmpeg from https://ffmpeg.org/download.html
Or use: winget install ffmpeg (if you have Windows Package Manager)"""
    else:
        return "Please install ffmpeg for your system from https://ffmpeg.org/download.html"

def show_post_install_message():
    """Display simple post-installation message"""
    print("\n" + "="*70)
    print("🎉 DocsRay Installation Complete!")
    print("="*70)
    print("\n📋 Complete setup with these two commands:\n")
    print("  1. docsray setup           # Install dependencies (ffmpeg, CUDA support)")
    print("  2. docsray download-models # Download AI models")
    print("\n" + "="*70 + "\n")

def show_hotfix_message():
    """Display the hotfix installation message (legacy compatibility)"""
    show_post_install_message()

def hotfix_check():
    """Main post-install function"""
    # Show the comprehensive post-install message
    show_post_install_message()
    return True

def main():
    """Run the post-installation script"""
    try:
        # Always show the post-install message when this script is run
        show_post_install_message()
    except Exception as e:
        print(f"Error during post-installation: {e}")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())