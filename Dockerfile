FROM python:3.11-slim


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