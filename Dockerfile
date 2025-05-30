FROM python:3.11-slim

# Install only essential system dependencies first
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Install the package
RUN pip install --no-cache-dir -e .

# Set environment variables
ENV DOCSRAY_MCP_MODE=1
ENV DOCSRAY_HOME=/app/.docsray

# Create necessary directories
RUN mkdir -p /app/.docsray/models /app/data/mcp_data/cache /app/data/original

# Start MCP server directly (models will download on first use)
CMD ["python", "-m", "docsray.mcp_server"]