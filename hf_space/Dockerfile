FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the package
COPY luther_mcp/ ./luther_mcp/

# HuggingFace Spaces uses /data for persistent storage
ENV CHROMA_PATH=/data/bible_chroma_db

# HuggingFace Spaces sets PORT=7860 automatically
CMD ["python", "-m", "luther_mcp", "--sse"]
