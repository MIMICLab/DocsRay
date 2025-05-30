FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    tesseract-ocr \
    tesseract-ocr-kor \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Create necessary directories
RUN mkdir -p /app/data/mcp_data/cache /app/data/original

# Download models during build to cache them in the image
# This speeds up container startup significantly
RUN python -m docsray.download_models

# Set environment variable for MCP mode
ENV DOCSRAY_MCP_MODE=1
ENV DOCSRAY_HOME=/app/.docsray

# Expose port (MCP uses stdio, but this is for health checks if needed)
EXPOSE 8000

# Start MCP server
CMD ["python", "-m", "docsray.mcp_server"]