# DocsRay 
[![PyPI Status](https://badge.fury.io/py/docsray.svg)](https://badge.fury.io/py/docsray)
[![license](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/MIMICLab/DocsRay/blob/main/LICENSE)
[![smithery badge](https://smithery.ai/badge/@MIMICLab/docsray)](https://smithery.ai/server/@MIMICLab/docsray)


A powerful PDF Question-Answering System that uses advanced embedding models and multimodal LLMs with Coarse-to-Fine search (RAG) approach. Features seamless MCP (Model Context Protocol) integration with Claude Desktop, comprehensive directory management capabilities, and visual content analysis.

## Try It Online
- [Demo on Intel Xeon CPU](https://docsray.com/) 

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
- **Multimodal AI**: Visual content analysis using Gemma-3-4B's image recognition capabilities
- **Multi-Model Support**: Uses BGE-M3, E5-Large, Gemma-3-1B, and Gemma-3-4B models
- **MCP Integration**: Seamless integration with Claude Desktop
- **Multiple Interfaces**: Web UI, API server, CLI, and MCP server
- **Directory Management**: Advanced PDF directory handling and caching
- **AI-Powered OCR**: LLM-based text extraction from scanned PDFs and images
- **Multi-Language**: Supports multiple languages including Korean and English
- **FAST_MODE**: Memory-efficient mode for resource-constrained environments

## 🎯 What's New in v0.3.x

### Visual Content Analysis
DocsRay now leverages multimodal AI to understand and describe visual content in PDFs:
- **Automatic Image Analysis**: Charts, graphs, diagrams, and figures are analyzed and described
- **AI-Powered OCR**: Replace traditional OCR with LLM-based text extraction
- **Vector Graphics Recognition**: Detects and analyzes PDF-native drawings and diagrams
- **Contextual Understanding**: Visual elements are described in relation to surrounding content

### Performance Optimization
- **FAST_MODE**: Automatically activated on low-memory systems (<4GB RAM)
- **Adaptive Processing**: Adjusts features based on available resources
- **Efficient Caching**: Smart caching system for processed documents

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

# Process PDF with visual analysis
extracted = pdf_extractor.extract_pdf_content(
    "document.pdf",
    analyze_visuals=True,  # Enable visual content analysis
    visual_analysis_interval=1  # Analyze every page
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

#### PDF Operations
- `List all PDFs in my current directory` - List available PDFs
- `Load the PDF named "paper.pdf"` - Load and process a PDF
- `Summarize this document` - Generate comprehensive summary
- `What are the main findings?` - Ask questions about loaded PDF

#### Visual Content Queries
- `What charts or figures are in this document?` - List visual elements
- `Describe the diagram on page 10` - Get specific visual descriptions
- `What data is shown in the graphs?` - Analyze data visualizations

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

### FAST_MODE (Automatic Memory Management)

DocsRay automatically detects available memory and enables FAST_MODE when needed:

| Available RAM | Mode | Features |
|--------------|------|----------|
| < 4GB | FAST_MODE | Text extraction only, no visual analysis |
| 4-8GB | Limited | Basic visual analysis on selected pages |
| > 8GB | Full | Complete visual analysis with multimodal AI |

FAST_MODE characteristics:
- Uses smaller models (Gemma-3-1B only)
- Disables image recognition and AI OCR
- Reduces maximum token context
- Maintains core Q&A functionality

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
| Gemma-3-4B | 4.1GB | Main answer generation & visual analysis |

**Total storage requirement**: ~8GB

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

1. **Check FAST_MODE status**:
   ```python
   from docsray import FAST_MODE, MAX_TOKENS
   print(f"FAST_MODE: {FAST_MODE}")
   print(f"MAX_TOKENS: {MAX_TOKENS}")
   ```

2. **Reduce visual analysis frequency**:
   ```python
   extracted = pdf_extractor.extract_pdf_content(
       pdf_path,
       analyze_visuals=True,
       visual_analysis_interval=5  # Analyze every 5th page
   )
   ```

3. **Use FAST_MODE explicitly**:
   ```bash
   export DOCSRAY_FAST_MODE=1
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

- **Documentation**: [https://docsray.com](https://docsray.com)
- **Issues**: [GitHub Issues](https://github.com/MIMICLab/DocsRay/issues)
- **Discussions**: [GitHub Discussions](https://github.com/MIMICLab/DocsRay/discussions)
