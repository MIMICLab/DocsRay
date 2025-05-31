# DocsRay 
[![PyPI Status](https://badge.fury.io/py/docsray.svg)](https://badge.fury.io/py/docsray)
[![license](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/MIMICLab/DocsRay/blob/main/LICENSE)
[![smithery badge](https://smithery.ai/badge/@MIMICLab/docsray)](https://smithery.ai/server/@MIMICLab/docsray)


A powerful PDF Question-Answering System that uses advanced embedding models and LLMs with Coarse-to-Fine search (RAG) approach. Features seamless MCP (Model Context Protocol) integration with Claude Desktop and comprehensive directory management capabilities.

## Try It Online
- [Demo on DocsRay Website](https://docsray.com/) 

## 🚀 Quick Start

```bash
# 1. Install DocsRay
pip install docsray

# 2. Download required models (approximately 8GB)
docsray download-models

# 3. Configure Claude Desktop integration (optional)
docsray configure-claude

# 4. Start using DocsRay
docsray web  # Launch Web UI
```

## 📋 Features

- **Advanced RAG System**: Coarse-to-Fine search for accurate document retrieval
- **Multi-Model Support**: Uses BGE-M3, E5-Large, Gemma-3-1B, and Trillion-7B models
- **MCP Integration**: Seamless integration with Claude Desktop
- **Multiple Interfaces**: Web UI, API server, CLI, and MCP server
- **Directory Management**: Advanced PDF directory handling and caching
- **OCR Support**: Automatic text extraction from scanned PDFs
- **Multi-Language**: Supports multiple languages including Korean and English

## 📁 Project Structure

```bash
DocsRay/
├── docsray/                    # Main package directory
│   ├── __init__.py
│   ├── chatbot.py             # Core chatbot functionality
│   ├── mcp_server.py          # MCP server with directory management
│   ├── app.py                 # FastAPI server
│   ├── web_demo.py            # Gradio web interface
│   ├── download_models.py     # Model download utility
│   ├── cli.py                 # Command-line interface
│   ├── inference/
│   │   ├── embedding_model.py # Embedding model implementations
│   │   └── llm_model.py       # LLM implementations
│   ├── scripts/
│   │   ├── pdf_extractor.py   # PDF content extraction
│   │   ├── chunker.py         # Text chunking logic
│   │   ├── build_index.py     # Search index builder
│   │   └── section_rep_builder.py
│   ├── search/
│   │   ├── section_coarse_search.py
│   │   ├── fine_search.py
│   │   └── vector_search.py
│   └── utils/
│       └── text_cleaning.py
├── setup.py                    # Package configuration
├── pyproject.toml             # Modern Python packaging
├── requirements.txt           # Dependencies
├── LICENSE
└── README.md
```

## 💾 Installation

### Basic Installation

```bash
pip install docsray
```

### Development Installation

```bash
git clone https://github.com/MIMICLab/DocsRay.git
cd DocsRay
pip install -e .
```

### GPU Support (Optional)

After installing DocsRay, you can enable GPU acceleration:

```bash
# For Metal (Apple Silicon)
CMAKE_ARGS=-DLLAMA_METAL=on FORCE_CMAKE=1 pip install llama-cpp-python --force-reinstall --upgrade --no-cache-dir

# For CUDA (NVIDIA)
CMAKE_ARGS=-DGGML_CUDA=on FORCE_CMAKE=1 pip install llama-cpp-python --force-reinstall --upgrade --no-cache-dir
```

### OCR Support (Optional)

For processing scanned PDFs:

```bash
# Debian/Ubuntu
sudo apt-get install tesseract-ocr tesseract-ocr-kor

# macOS
brew install tesseract tesseract-lang

# Windows
# Download installer from: https://github.com/UB-Mannheim/tesseract/wiki
```

## 🎯 Usage

### Command Line Interface

```bash
# Download models (required for first-time setup)
docsray download-models

# Check model status
docsray download-models --check

# Process a PDF
docsray process /path/to/document.pdf

# Ask questions about a processed PDF
docsray ask "What is the main topic?" --pdf document.pdf

# Start web interface
docsray web

# Start API server
docsray api --pdf /path/to/document.pdf --port 8000

docsray api --pdf /path/to/document.pdf --system-prompt "You are a technical document assistant."

docsray api --pdf /path/to/document.pdf --reload

# Start MCP server
docsray mcp
```

### Web Interface

```bash
docsray web
```

Access the web interface at `http://localhost:44665`. Default credentials:
- Username: `admin`
- Password: `password`

### API Server

```bash
docsray api
```

Example API usage:

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the main topic of this document?"}'
```

### Python API

```python
from docsray import PDFChatBot

# Initialize chatbot with processed data
chatbot = PDFChatBot(sections, chunk_index)

# Ask questions
answer, references = chatbot.answer("What are the key findings?")
```

## 🔌 MCP (Model Context Protocol) Integration

### Setup

1. **Configure Claude Desktop**:
   ```bash
   docsray configure-claude
   ```

2. **Restart Claude Desktop**

3. **Start using DocsRay in Claude**

### MCP Commands in Claude

#### Directory Management
- `What's my current PDF directory?` - Show current working directory
- `Set my PDF directory to /path/to/documents` - Change working directory
- `Show me information about /path/to/pdfs` - Get directory details

#### PDF Operations
- `List all PDFs in my current directory` - List available PDFs
- `Load the PDF named "paper.pdf"` - Load and process a PDF
- `What are the main findings?` - Ask questions about loaded PDF

### Advanced MCP Usage

```
# Multi-directory workflow
1. Check current directory
2. List PDFs in a specific directory
3. Change to a new directory
4. Load a PDF
5. Ask questions with deep search enabled
```

## ⚙️ Configuration

### Environment Variables

```bash
# Custom data directory (default: ~/.docsray)
export DOCSRAY_HOME=/path/to/custom/directory

# GPU configuration
export DOCSRAY_USE_GPU=1
export DOCSRAY_GPU_LAYERS=-1  # Use all layers on GPU

# Model paths (optional)
export DOCSRAY_MODEL_DIR=/path/to/models
```

### Data Storage

DocsRay stores data in the following locations:
- **Models**: `~/.docsray/models/`
- **Cache**: `~/.docsray/cache/`
- **User Data**: `~/.docsray/data/`

## 🤖 Models

DocsRay uses the following models (automatically downloaded):

| Model | Size | Purpose |
|-------|------|---------|
| BGE-M3 | 1.7GB | Multilingual embedding model |
| E5-Large | 1.2GB | Multilingual embedding model |
| Gemma-3-1B | 1.1GB | Query enhancement and light tasks |
| Trillion-7B | 4.1GB | Main answer generation |

**Total storage requirement**: ~8GB

## 🔧 Troubleshooting

### Model Download Issues

```bash
# Check model status
docsray download-models --check

# Manual download (if automatic download fails)
# Download models from HuggingFace and place in ~/.docsray/models/
```

### GPU Support Issues

```bash
# Reinstall with GPU support
pip uninstall llama-cpp-python

# For CUDA
CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python --no-cache-dir

# For Metal
CMAKE_ARGS="-DLLAMA_METAL=on" pip install llama-cpp-python --no-cache-dir
```

### MCP Connection Issues

1. Ensure all models are downloaded:
   ```bash
   docsray download-models
   ```

2. Reconfigure Claude Desktop:
   ```bash
   docsray configure-claude
   ```

3. Restart Claude Desktop completely

### Performance Optimization

- Use SSD storage for better performance
- Keep PDF files in local directories
- Clear cache periodically:
  ```bash
  rm -rf ~/.docsray/cache/*
  ```

## 📚 Advanced Usage

### Processing Pipeline

For manual processing:

```bash
# 1. Extract PDF content
python -m docsray.scripts.pdf_extractor

# 2. Create chunks
python -m docsray.scripts.chunker

# 3. Build embeddings
python -m docsray.scripts.build_index

# 4. Generate section representations
python -m docsray.scripts.section_rep_builder
```

### Custom System Prompts

Create custom prompts for specific use cases:

```python
from docsray import PDFChatBot

custom_prompt = """
You are a technical document assistant specializing in research papers.
Focus on methodology and results when answering questions.
"""

chatbot = PDFChatBot(sections, chunk_index, system_prompt=custom_prompt)
```

### Batch Processing

Process multiple PDFs:

```bash
for pdf in *.pdf; do
    docsray process "$pdf"
done
```

## 🛠️ Development

### Setting Up Development Environment

```bash
# Clone repository
git clone https://github.com/yourusername/docsray.git
cd docsray

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e .[dev]

# Run tests
pytest tests/
```

### Building and Publishing

```bash
# Build package
python -m build

# Upload to TestPyPI
twine upload --repository testpypi dist/*

# Upload to PyPI
twine upload dist/*
```

## 📄 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) file for details.

**Note**: Individual model licenses may have different requirements. Please check:
- BAAI/bge-m3: MIT License
- intfloat/multilingual-e5-large: MIT License
- gemma3-1B-it: Gemma Terms of Use
- Trillion-7B-preview: Apache-2.0 License

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

