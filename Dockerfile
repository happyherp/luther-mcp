FROM python:3.11-slim

WORKDIR /app

# Install git for sparse clone, then clean up after
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY luther_mcp/ ./luther_mcp/

# Pre-download the embedding model so it's baked into the image
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-small')"

# Download Bible SQLite files and build the ChromaDB index at image build time
RUN git clone --depth 1 --filter=blob:none --sparse \
        https://github.com/scrollmapper/bible_databases /tmp/bible_db && \
    cd /tmp/bible_db && \
    git sparse-checkout set \
        "formats/sqlite/GerBoLut.db" \
        "formats/sqlite/KJV.db" \
        "formats/sqlite/NHEB.db" && \
    git checkout

ENV BIBLE_DB_PATH=/tmp/bible_db/formats/sqlite
ENV CHROMA_PATH=/app/bible_chroma_db

RUN python -m luther_mcp index

# Clean up SQLite files — index is all we need at runtime
RUN rm -rf /tmp/bible_db

# HuggingFace Spaces sets PORT=7860 automatically
CMD ["python", "-m", "luther_mcp", "--sse"]
