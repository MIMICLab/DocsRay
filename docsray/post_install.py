#!/usr/bin/env python3
"""Post-installation script for DocsRay"""

def show_hotfix_message():
    """Display the hotfix installation message"""
    print("\n" + "="*70)
    print("🎉 DocsRay Installation Complete!")
    print("="*70)
    print("\n# 1-1. Hotfix (Temporary)")
    print("# Hotfix: Use the forked version of llama-cpp-python for Gemma3 Support")
    print("# Note: This is a temporary fix until the official library supports Gemma3")
    print("# Install the forked version of llama-cpp-python")
    print("\npip install git+https://github.com/kossum/llama-cpp-python.git@main\n")
    print("\n# For Metal (Apple Silicon)\n")
    print("CMAKE_ARGS=-DLLAMA_METAL=on FORCE_CMAKE=1 pip install git+https://github.com/kossum/llama-cpp-python.git@main --force-reinstall --upgrade --no-cache-dir\n")
    print("\n# For CUDA (NVIDIA)\n")
    print("\nCMAKE_ARGS=-DGGML_CUDA=on FORCE_CMAKE=1 pip install git+https://github.com/kossum/llama-cpp-python.git@main --force-reinstall --upgrade --no-cache-dir\n")
    print("="*70)
    print("\nAfter installing the hotfix, download the required models:")
    print("docsray download-models")
    print("\nThen you can start using DocsRay!")
    print("="*70 + "\n")

def hotfix_check():
    """Main post-install function"""
    # Check if llama-cpp-python needs update
    #Identity function for now
    pass
def main():
    """Run the post-installation hotfix check"""
    print("Running DocsRay post-installation hotfix check...")
    hotfix_check()
    print("Post-installation check completed.")

if __name__ == "__main__":
    main()