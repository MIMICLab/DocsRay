# DocsRay 
[![PyPI Status](https://badge.fury.io/py/docsray.svg)](https://badge.fury.io/py/docsray)
[![license](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/MIMICLab/DocsRay/blob/main/LICENSE)
[![Downloads](https://pepy.tech/badge/docsray)](https://pepy.tech/project/docsray)
[![Verified on MseeP](https://mseep.ai/badge.svg)](https://mseep.ai/app/f6dfcc65-8ee3-4ad1-9101-88b6dbdcf37b)

**[🌐 Live Demo (Base Model)](https://docsray.com/)**

A powerful Universal Document Question-Answering System that uses advanced embedding models and multimodal LLMs with Coarse-to-Fine search (RAG) approach. Features seamless MCP (Model Context Protocol) integration with Claude Desktop, comprehensive directory management capabilities, visual content analysis, and intelligent hybrid OCR system.

## 🚀 Quick Start

```bash
# 1. Install DocsRay
pip install docsray

# 1-1. Tesseract OCR (optional)
# For faster OCR, install Tesseract with appropriate language pack.

#pip install pytesseract
#sudo apt-get install tesseract-ocr   # Debian/Ubuntu
#sudo apt-get install tesseract-ocr-kor
#brew install tesseract-ocr   # MacOS
#brew install tesseract-ocr-kor

# 1-2. llama_cpp_python rebuild (recommended for CUDA)
#CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python==0.3.9 --upgrade --force-reinstall --no-cache-dir

# 2. Download models (choose your preferred size)
docsray download-models --model-type lite   # 4b model (~3GB)
# docsray download-models --model-type base  # 12b model (~8GB) 
# docsray download-models --model-type pro   # 27b model (~16GB)

# 3. Configure Claude Desktop integration (optional)
docsray configure-claude

# 4. Start using DocsRay
docsray web                                 # Launch Web UI
docsray api                                 # Start API server
```

## 📋 Core Features

- **🧠 Advanced RAG System**: Coarse-to-Fine search for accurate document retrieval
- **👁️ Multimodal AI**: Visual content analysis using Gemma-3 vision capabilities
- **🔄 Hybrid OCR**: Intelligent selection between AI-powered OCR and Pytesseract
- **⚡ Adaptive Performance**: Automatically optimizes based on system resources
- **🎯 Flexible Model Selection**: Choose between lite (4b), base (12b), and pro (27b) models
- **🔌 MCP Integration**: Seamless integration with Claude Desktop
- **🌐 Multiple Interfaces**: Web UI, API server, CLI, and MCP server
- **📁 Universal Document Support**: 30+ file formats with automatic conversion
- **🌍 Multi-Language**: Korean, English, and other languages supported

## 🎯 What's New in v1.7.1

### Auto-Restart and Timeout Features
- **Auto-Restart Support**: Web, API, and MCP servers now support automatic restart on crashes
- **Optional Timeout**: `--timeout` parameter only applies when explicitly specified
- **Optional Page Limits**: `--pages` parameter only applies when explicitly specified  
- **Request Timeout for API**: API server can auto-restart if request processing exceeds timeout
- **Unlimited Retries**: `--max-retries` is optional; if not specified, servers will retry indefinitely

### v1.7.0: Breaking Change - Enhanced Embedding Method
- **Improved Embedding Synthesis**: Changed from element-wise addition to concatenation
- **IMPORTANT**: This change requires reindexing of existing documents
- **Better Accuracy**: Concatenation preserves more information from both embedding models

## 📖 Usage Guide

### Model Management
```bash
# Download specific model type
docsray download-models --model-type lite   # Fast, lower quality
docsray download-models --model-type base   # Balanced performance
docsray download-models --model-type pro    # Best quality, slower

# Force re-download existing models
docsray download-models --model-type base --force

# Check model status
docsray download-models --check
```

### Document Processing
```bash
# Process any document type
docsray process document.pdf --model-type base
docsray process report.docx --timeout 300
docsray process spreadsheet.xlsx --no-visuals

# Ask questions about processed documents
docsray ask document.pdf "What are the key findings?"
docsray ask report.docx "Summarize the conclusions" --model-type pro
```

### Web Interface
```bash
# Basic web interface
docsray web

# Advanced options
docsray web --model-type base --port 8080
docsray web --auto-restart                    # Auto-restart with unlimited retries
docsray web --auto-restart --max-retries 5    # Auto-restart with 5 retry limit
docsray web --timeout 300 --pages 10          # Process max 10 pages, 5min timeout
```

### API Server
```bash
# Start API server
docsray api --port 8000

# With auto-restart and timeout
docsray api --auto-restart                     # Unlimited retries
docsray api --auto-restart --timeout 600       # 10min timeout per request

# API accepts document paths per request
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{
    "document_path": "/path/to/document.pdf",
    "question": "What is the main topic?",
    "use_coarse_search": true
  }'

# Check cache info and clear if needed
curl http://localhost:8000/cache/info
curl -X POST http://localhost:8000/cache/clear
```

### Performance Testing
```bash
# Basic performance test
docsray perf-test document.pdf "What is this about?"

# Advanced testing
docsray perf-test document.pdf "Analyze key points" \
  --iterations 5 --port 8000 --host localhost
```

### MCP Integration (Claude Desktop)
```bash
# Configure Claude Desktop
docsray configure-claude

# Start MCP server
docsray mcp --auto-restart
```

## 📁 Supported File Formats

**Office Documents**: Word (.docx, .doc), Excel (.xlsx, .xls), PowerPoint (.pptx, .ppt)  
**Text Formats**: Plain Text (.txt), Markdown (.md), HTML (.html)  
**Images**: JPEG, PNG, GIF, BMP, TIFF, WebP  
**Korean Documents**: HWP (.hwp, .hwpx)  
**PDFs**: Native PDF support with visual analysis

## 🛠️ Advanced Configuration

### Environment Variables
```bash
export DOCSRAY_MODEL_TYPE=base           # Set default model type
export DOCSRAY_DISABLE_VISUALS=1         # Disable visual analysis
export DOCSRAY_DEBUG=1                   # Enable debug mode
export DOCSRAY_HOME=/custom/path         # Custom data directory
```

### Python API
```python
from docsray import PDFChatBot
from docsray.scripts import pdf_extractor, chunker, build_index, section_rep_builder

# Process document
extracted = pdf_extractor.extract_content("document.pdf", analyze_visuals=True)
chunks = chunker.process_extracted_file(extracted)
chunk_index = build_index.build_chunk_index(chunks)
sections = section_rep_builder.build_section_reps(extracted["sections"], chunk_index)

# Create chatbot and ask questions
chatbot = PDFChatBot(sections, chunk_index)
answer, references = chatbot.answer("What are the key points?")
```


## 🔧 System Requirements

### Hardware Requirements
- **CPU Mode**: Any system with 4GB+ RAM
- **GPU Acceleration**: CUDA-compatible GPU or Apple Silicon (MPS)
- **Storage**: 3-16GB depending on model type chosen

### Performance Modes (Auto-detected)
| System Memory | Mode | Models | Max Tokens |
|--------------|------|--------|------------|
| < 16GB | FAST | Q4 quantized | 8K |
| 16-32GB | STANDARD | Q8 quantized | 16K |
| > 32GB | FULL_FEATURE | F16 precision | 32K |

## 🐛 Troubleshooting

### Common Issues
```bash
# Check system status
docsray download-models --check

# Re-download corrupted models
docsray download-models --force

# Debug mode for detailed logs
DOCSRAY_DEBUG=1 docsray web
```

### Performance Issues
- Use `--model-type lite` for faster processing
- Enable `--no-visuals` for text-only documents
- Increase `--timeout` for large documents
- Use auto-restart for stability: `--auto-restart`

## 📊 Performance Benchmarks

Run your own benchmarks:
```bash
# Test API performance
docsray perf-test document.pdf "test question" --iterations 10

# Compare model types
docsray perf-test document.pdf "test question" --model-type lite
docsray perf-test document.pdf "test question" --model-type base
```

## 🤝 Contributing

We welcome contributions! Please check our [GitHub repository](https://github.com/your-repo/DocsRay) for:
- Bug reports and feature requests
- Code contributions and pull requests
- Documentation improvements

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🔗 Links

- **Live Demo (Base Model)**: https://docsray.com/
- **PyPI Package**: https://pypi.org/project/docsray/
- **Documentation**: https://github.com/your-repo/DocsRay
- **Issues & Support**: https://github.com/your-repo/DocsRay/issues
