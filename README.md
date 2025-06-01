# DocsRay 
[![PyPI Status](https://badge.fury.io/py/docsray.svg)](https://badge.fury.io/py/docsray)
[![license](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/MIMICLab/DocsRay/blob/main/LICENSE)
[![smithery badge](https://smithery.ai/badge/@MIMICLab/docsray)](https://smithery.ai/server/@MIMICLab/docsray)


A powerful PDF Question-Answering System that uses advanced embedding models and multimodal LLMs with Coarse-to-Fine search (RAG) approach. Features seamless MCP (Model Context Protocol) integration with Claude Desktop, comprehensive directory management capabilities, visual content analysis, and intelligent hybrid OCR system.

## Try It Online
- [Demo on H100 GPU](https://docsray.com/) 

## 🚀 Quick Start

```bash
# 1. Install DocsRay
pip install docsray

# 1-1. Hotfix (Temporary)
# Hotfix: Use the forked version of llama-cpp-python for Gemma3 Support
# Note: This is a temporary fix until the official library supports Gemma3
# Install the forked version of llama-cpp-python
pip install git+https://github.com/kossum/llama-cpp-python.git@main

# 2. Download required models (approximately 8GB)
docsray download-models

# 3. Configure Claude Desktop integration (optional)
docsray configure-claude

# 4. Start using DocsRay
docsray web  # Launch Web UI
```

## 📋 Features

- **Advanced RAG System**: Coarse-to-Fine search for accurate document retrieval
- **Multimodal AI**: Visual content analysis using Gemma-3-4B's image recognition capabilities
- **Hybrid OCR System**: Intelligent selection between AI-powered OCR and traditional Pytesseract
- **Adaptive Performance**: Automatically optimizes based on available system resources
- **Multi-Model Support**: Uses BGE-M3, E5-Large, Gemma-3-1B, and Gemma-3-4B models
- **MCP Integration**: Seamless integration with Claude Desktop
- **Multiple Interfaces**: Web UI, API server, CLI, and MCP server
- **Directory Management**: Advanced PDF directory handling and caching
- **Multi-Language**: Supports multiple languages including Korean and English
- **Smart Resource Management**: FAST_MODE, Standard, and FULL_FEATURE_MODE based on system specs
- **Universal Document Support**: Automatically converts 30+ file formats to PDF for processing
- **Smart File Conversion**: Handles Office documents, images, HTML, Markdown, and more

## 🎯 What's New in v1.1.X
### Universal Document Support
DocsRay now automatically converts various document formats to PDF for processing:

#### Supported File Formats

**Office Documents**
- Microsoft Word (.docx, .doc)
- Microsoft Excel (.xlsx, .xls)
- Microsoft PowerPoint (.pptx, .ppt)
- OpenDocument formats (.odt, .ods, .odp)

**Text Formats**
- Plain Text (.txt)
- Markdown (.md)
- Rich Text Format (.rtf)
- reStructuredText (.rst)

**Web Formats**
- HTML (.html, .htm)
- XML (.xml)

**Image Formats**
- JPEG (.jpg, .jpeg)
- PNG (.png)
- GIF (.gif)
- BMP (.bmp)
- TIFF (.tiff, .tif)
- WebP (.webp)

**E-book Formats**
- EPUB (.epub)
- MOBI (.mobi)

### Automatic Conversion
Simply load any supported file type, and DocsRay will:
1. Automatically detect the file format
2. Convert it to PDF in the background
3. Process it with all the same features as native PDFs
4. Clean up temporary files automatically

```python
# Works with any supported format!
docsray process /path/to/document.docx
docsray process /path/to/spreadsheet.xlsx
docsray process /path/to/image.png
```

### Hybrid OCR System
DocsRay now features an intelligent hybrid OCR system that automatically selects the optimal OCR method based on your system resources:

- **FULL_FEATURE_MODE (RAM > 32GB)**: AI-powered OCR using Gemma-3-4B model
  - Accurately recognizes complex layouts and multilingual text
  - Understands context when extracting text from tables, charts, and diagrams
  - Significantly improves text quality from scanned PDFs

- **Standard Mode (RAM 8-32GB)**: Traditional Pytesseract-based OCR
  - Stable and fast text extraction
  - Multi-language support (including Korean)
  
- **FAST_MODE (RAM < 8GB)**: OCR disabled
  - Memory efficiency prioritized
  - Processes only PDFs with embedded text

### Adaptive Performance Optimization
Automatically detects system resources and optimizes performance:

```python
# Automatic resource detection and mode configuration
if available_ram >= 32GB:
    FULL_FEATURE_MODE = True  # All features enabled
elif available_ram < 16GB:
    FAST_MODE = True  # Lightweight mode
else:
    # Standard mode (balanced performance)
```

### Enhanced MCP Commands
- **Cache Management**: `clear_all_cache`, `get_cache_info`
- **Improved Summarization**: Batch processing with section-by-section caching
- **Detail Levels**: Adjustable summary detail (brief/standard/detailed)

## 📊 Performance Optimization Guide

### Recommended Settings by Memory

| System Memory |    Mode   | OCR | Visual Analysis | Max Tokens |
|--------------|------------|--------------|--------------|------------|
| < 8GB | FAST_MODE(Q4) | ✅ (Pytesseract) | ✅ |16K |
| 8-16GB | FAST_MODE (Q4) | ✅ (Pytesseract) | ✅ | 32K |
| 16-32GB | STANDARD (Q8) | ✅ (Pytesseract) | ✅ | 32K |
| > 32GB | FULL_FEATURE (Q8) | ✅ (AI OCR) | ✅  | 128K |

## 📁 Project Structure

```bash
DocsRay/
├── docsray/                    # Main package directory
│   ├── __init__.py            # Package init with FAST_MODE detection
│   ├── chatbot.py             # Core chatbot functionality
│   ├── mcp_server.py          # MCP server with directory management
│   ├── app.py                 # FastAPI server
│   ├── web_demo.py            # Gradio web interface
│   ├── download_models.py     # Model download utility
│   ├── cli.py                 # Command-line interface
│   ├── inference/
│   │   ├── embedding_model.py # Embedding model implementations
│   │   └── llm_model.py       # LLM implementations (including multimodal)
│   ├── scripts/
│   │   ├── pdf_extractor.py   # Enhanced PDF extraction with visual analysis
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

### GPU Support (Optional but Recommended)

After installing DocsRay, you can enable GPU acceleration for better performance:

```bash
# For Metal (Apple Silicon)
CMAKE_ARGS=-DLLAMA_METAL=on FORCE_CMAKE=1 pip install llama-cpp-python --force-reinstall --upgrade --no-cache-dir

# For CUDA (NVIDIA)
CMAKE_ARGS=-DGGML_CUDA=on FORCE_CMAKE=1 pip install llama-cpp-python --force-reinstall --upgrade --no-cache-dir
```

### File Conversion Dependencies (Optional)

For best file conversion results, install system dependencies:

```bash
# Ubuntu/Debian
sudo apt-get install libreoffice pandoc wkhtmltopdf

# macOS
brew install libreoffice pandoc wkhtmltopdf

# Windows
# Download and install:
# - LibreOffice: https://www.libreoffice.org/download/
# - Pandoc: https://pandoc.org/installing.html
# - wkhtmltopdf: https://wkhtmltopdf.org/downloads.html
```

Python packages for conversion are included in the base installation, but system tools provide better results for complex documents.

## 🎯 Usage

### Command Line Interface

```bash
# Download models (required for first-time setup)
docsray download-models

# Check model status
docsray download-models --check

# Process a PDF with visual analysis
docsray process /path/to/document.pdf

# Ask questions about a processed PDF
docsray ask "What is the main topic?" --pdf document.pdf

# Start web interface
docsray web

# Start API server
docsray api --pdf /path/to/document.pdf --port 8000

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

Features:
- Upload and process PDFs with visual content analysis
- Ask questions about document content including images and charts
- Manage multiple PDFs with caching
- Customize system prompts

### API Server

```bash
docsray api --pdf /path/to/document.pdf
```

Example API usage:

```bash
# Ask a question
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What does the chart on page 5 show?"}'

# Get PDF info
curl http://localhost:8000/info
```

### Python API

```python
from docsray import PDFChatBot
from docsray.scripts import pdf_extractor, chunker, build_index, section_rep_builder

# Process any document type - auto-conversion handled internally
extracted = pdf_extractor.extract_content(
    "report.docx",  # Can be DOCX, XLSX, PNG, HTML, etc.
    analyze_visuals=True,
    visual_analysis_interval=1
)

# Create chunks and build index
chunks = chunker.process_extracted_file(extracted)
chunk_index = build_index.build_chunk_index(chunks)
sections = section_rep_builder.build_section_reps(extracted["sections"], chunk_index)

# Initialize chatbot
chatbot = PDFChatBot(sections, chunk_index)

# Ask questions
answer, references = chatbot.answer("What are the key trends shown in the graphs?")
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

#### Document Operations (Updated)
- `List all documents in my current directory` - List all supported files (not just PDFs)
- `Load the document named "report.docx"` - Load any supported file type
- `What file types are supported?` - Show list of supported formats

#### Visual Content Queries
- `What charts or figures are in this document?` - List visual elements
- `Describe the diagram on page 10` - Get specific visual descriptions
- `What data is shown in the graphs?` - Analyze data visualizations

#### Cache Management (New)
- `Clear all cache` - Remove all cached files
- `Show cache info` - Display cache statistics and details

## ⚙️ Configuration

### Environment Variables

```bash
# Custom data directory (default: ~/.docsray)
export DOCSRAY_HOME=/path/to/custom/directory

# Force specific mode
export DOCSRAY_FAST_MODE=1  # Force FAST_MODE

# GPU configuration
export DOCSRAY_USE_GPU=1
export DOCSRAY_GPU_LAYERS=-1  # Use all layers on GPU

# Model paths (optional)
export DOCSRAY_MODEL_DIR=/path/to/models
```

### Programmatic Mode Detection

```python
from docsray import FAST_MODE, FULL_FEATURE_MODE, MAX_TOKENS

print(f"Fast Mode: {FAST_MODE}")
print(f"Full Feature Mode: {FULL_FEATURE_MODE}")
print(f"Max Tokens: {MAX_TOKENS}")
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
| bge-m3 | 1.7GB | Multilingual embedding model |
| multilingual-e5-Large | 1.2GB | Multilingual embedding model |
| Gemma-3-1B | 1.1GB | Query enhancement and light tasks |
| Gemma-3-4B | 4.1GB | Main answer generation & visual analysis |

**Total storage requirement**: ~8GB

## 💡 Usage Recommendations by Scenario

### 1. Bulk PDF Processing (Server Environment)
- Recommended: FULL_FEATURE_MODE (ensure sufficient RAM)
- GPU acceleration essential
- Adjust visual_analysis_interval for batch processing

### 2. Personal Laptop Environment
- Recommended: Standard mode
- Switch to FAST_MODE when needed
- Analyze visuals only on important pages

### 3. Resource-Constrained Environment
- Use FAST_MODE
- Process text-based PDFs only
- Leverage caching aggressively

## 🎨 Visual Content Analysis Examples

### Chart Analysis
```
[Figure 1 on page 3]: This is a bar chart showing quarterly revenue growth 
from Q1 2023 to Q4 2023. The y-axis represents revenue in millions of dollars 
ranging from 0 to 50. Each quarter shows progressive growth with Q1 at $12M, 
Q2 at $18M, Q3 at $28M, and Q4 at $42M. The trend indicates strong 
year-over-year growth of approximately 250%.
```

### Diagram Recognition
```
[Figure 2 on page 5]: A flowchart diagram illustrating the data processing 
pipeline. The flow starts with "Data Input" at the top, branches into three 
parallel processes: "Validation", "Transformation", and "Enrichment", which 
then converge at "Data Integration" before ending at "Output Database".
```

### Table Extraction
```
[Table 1 on page 7]: A comparison table with 4 columns (Product, Q1 Sales, 
Q2 Sales, Growth %) and 5 rows of data. Product A shows the highest growth 
at 45%, while Product C has the highest absolute sales in Q2 at $2.3M.
```

## 🔧 Troubleshooting

### Model Download Issues

```bash
# Check model status
docsray download-models --check

# Manual download (if automatic download fails)
# Download models from HuggingFace and place in ~/.docsray/models/
```

### Memory Issues

If you encounter out-of-memory errors:

1. **Check current mode**:
   ```python
   from docsray import FAST_MODE, MAX_TOKENS
   print(f"FAST_MODE: {FAST_MODE}")
   print(f"MAX_TOKENS: {MAX_TOKENS}")
   ```

2. **Force FAST_MODE**:
   ```bash
   export DOCSRAY_FAST_MODE=1
   ```

3. **Reduce visual analysis frequency**:
   ```python
   extracted = pdf_extractor.extract_pdf_content(
       pdf_path,
       analyze_visuals=True,
       visual_analysis_interval=5  # Analyze every 5th page
   )
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

3. Check MCP server logs:
   ```bash
   docsray mcp
   ```

### OCR Language Errors

```bash
# Install Korean tesseract data
sudo apt-get install tesseract-ocr-kor
```

### File Conversion Issues

#### Office Documents Not Converting
```bash
# Install LibreOffice for best results
sudo apt-get install libreoffice  # Ubuntu/Debian
brew install libreoffice  # macOS
```

#### HTML/Web Files Not Converting
```bash
# Install wkhtmltopdf
sudo apt-get install wkhtmltopdf  # Ubuntu/Debian
brew install wkhtmltopdf  # macOS

# Or use weasyprint (Python-only alternative)
pip install weasyprint
```

#### Missing Converter Warning
If you see "No suitable converter found":
1. Check system dependencies are installed
2. Verify Python packages: `pip install docsray[conversion]`
3. Try alternative converters (LibreOffice > docx2pdf > pandoc)

## 📚 Advanced Usage

### Custom Visual Analysis

```python
from docsray.scripts.pdf_extractor import extract_pdf_content

# Fine-tune visual analysis
extracted = extract_pdf_content(
    "technical_report.pdf",
    analyze_visuals=True,
    visual_analysis_interval=1  # Every page
)

# Access visual descriptions
for i, page_text in enumerate(extracted["pages_text"]):
    if "[Figure" in page_text or "[Table" in page_text:
        print(f"Visual content found on page {i+1}")
```

### Batch Processing with Visual Analysis

```bash
#!/bin/bash
for pdf in *.pdf; do
    echo "Processing $pdf with visual analysis..."
    docsray process "$pdf" --analyze-visuals
done
```

### Custom System Prompts for Visual Content

```python
from docsray import PDFChatBot

visual_prompt = """
You are a document assistant specialized in analyzing visual content.
When answering questions:
1. Reference specific figures, charts, and tables by their descriptions
2. Integrate visual information with text content
3. Highlight data trends and patterns shown in visualizations
"""

chatbot = PDFChatBot(sections, chunk_index, system_prompt=visual_prompt)
```
### Batch Document Processing (Mixed Formats)

```bash
#!/bin/bash
# Process all supported documents in a directory
for file in *.{pdf,docx,xlsx,pptx,txt,md,html,png,jpg}; do
    if [[ -f "$file" ]]; then
        echo "Processing $file..."
        docsray process "$file"
    fi
done
```

### Programmatic Format Detection

```python
from docsray.scripts.file_converter import FileConverter

converter = FileConverter()

# Check if file is supported
if converter.is_supported("presentation.pptx"):
    print("File is supported!")
    
# Get all supported formats
formats = converter.get_supported_formats()
for ext, description in formats.items():
    print(f"{ext}: {description}")
```

## 🛠️ Development

### Setting Up Development Environment

```bash
# Clone repository
git clone https://github.com/MIMICLab/DocsRay.git
cd DocsRay

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e .[dev]

# Run tests
pytest tests/
```

### Contributing

Contributions are welcome! Areas of interest:
- Additional multimodal model support
- Enhanced table extraction algorithms
- Support for more document formats
- Performance optimizations
- UI/UX improvements

## 📄 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) file for details.

**Note**: Individual model licenses may have different requirements:
- BAAI/bge-m3: MIT License
- intfloat/multilingual-e5-large: MIT License
- gemma-3-1B-it: Gemma Terms of Use
- gemma-3-4B-it: Gemma Terms of Use

## 🤝 Support

- **Web Demo**: [https://docsray.com](https://docsray.com)
- **Issues**: [GitHub Issues](https://github.com/MIMICLab/DocsRay/issues)
- **Discussions**: [GitHub Discussions](https://github.com/MIMICLab/DocsRay/discussions)