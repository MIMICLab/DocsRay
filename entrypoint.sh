#!/bin/bash
set -e

# Check if models exist
if [ ! -f "/app/.docsray/models/bge-m3-gguf/bge-m3-Q8_0.gguf" ]; then
    echo "Models not found. Downloading required models..."
    python -m docsray.download_models --check || python -m docsray.download_models
else
    echo "Models already present, skipping download."
fi

# Execute the main command
exec "$@"