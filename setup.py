from setuptools import setup, find_packages
from setuptools.command.install import install
from setuptools.command.develop import develop
import os
import sys

# Read the contents of README file
this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

# Read requirements
with open('requirements.txt') as f:
    requirements = f.read().splitlines()

class PostInstallCommand(install):
    """Post-installation for installation mode."""
    def run(self):
        install.run(self)
        self.show_post_install_message()
        
    def show_post_install_message(self):
        """Display post-install message"""
        print("\n" + "="*70)
        print("🎉 DocsRay Installation Complete!")
        print("="*70)
        print("\n# 1-1. Hotfix (Temporary)")
        print("# Hotfix: Use the forked version of llama-cpp-python for Gemma3 Support")
        print("# Note: This is a temporary fix until the official library supports Gemma3")
        print("# Install the forked version of llama-cpp-python")
        print("\npip install git+https://github.com/kossum/llama-cpp-python.git@main\n")
        print("="*70)
        print("\nAfter installing the hotfix, download the required models:")
        print("docsray download-models")
        print("\nThen you can start using DocsRay!")
        print("="*70 + "\n")

class PostDevelopCommand(develop):
    """Post-installation for development mode."""
    def run(self):
        develop.run(self)
        # Import and run the post-install check
        post_install = PostInstallCommand(self.distribution)
        post_install.show_post_install_message()

setup(
    name="docsray",
    version="1.0.2",
    author="Taehoon Kim",
    author_email="taehoonkim@sogang.ac.kr",
    description="PDF Question-Answering System with MCP Integration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/MIMICLab/DocsRay",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        'console_scripts': [
            'docsray=docsray.cli:main',
            'docsray-web=docsray.web_demo:main',
            'docsray-api=docsray.app:main',
            'docsray-mcp=docsray.mcp_server:main',
            'docsray-post-install=docsray.post_install:main',
        ],
    },
    include_package_data=True,
    cmdclass={
        'install': PostInstallCommand,
        'develop': PostDevelopCommand,
    },
)