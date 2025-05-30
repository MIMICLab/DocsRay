FROM python:3.11-slim

# Install build dependencies for llama-cpp-python
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files
COPY . .

# Install Python package
RUN pip install --no-cache-dir -e .

# Create necessary directories
RUN mkdir -p /app/.docsray/models /app/data/mcp_data/cache /app/data/original

# Set environment variables
ENV DOCSRAY_MCP_MODE=1
ENV DOCSRAY_HOME=/app/.docsray

# Start MCP server
CMD ["python", "-m", "docsray.mcp_server"]