FROM tgisaturday/docsray-mcp:latest

WORKDIR /app

CMD ["python", "-m", "docsray.mcp_server"]