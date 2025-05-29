# setup.py
import os
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="docsray",
    version="0.1.0",
    author="Taehoon Kim",
    author_email="taehoonkim@sogang.ac.kr",
    description="PDF Question-Answering System with MCP Integration",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/MIMICLab/DocsRay",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12"
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "docsray=docsray.cli:main",
            "docsray-mcp=docsray.mcp_server:main",
            "docsray-web=docsray.web_demo:main",
            "docsray-api=docsray.app:main",
            "docsray-download-models=docsray.download_models:main",
        ],
    },
    include_package_data=True,
    package_data={
        "docsray": ["data/*", "data/**/*"],
    },
    extras_require={
        "dev": ["pytest", "black", "flake8"],
        "gpu": ["llama-cpp-python"],  
    },
)