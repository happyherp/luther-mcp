---
title: Luther Bible MCP
emoji: 📖
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# Luther Bible MCP Server

Semantic search over the German Luther Bible (1545), King James Version, and New Heart English Bible. Backed by `intfloat/multilingual-e5-small` embeddings — no API key required.

Cross-lingual search works out of the box: query in English to find German verses, or vice versa.

**Hosted on HuggingFace Spaces:** [AIFreund/luther-bible](https://huggingface.co/spaces/AIFreund/luther-bible)

---

## Quickstart — hosted, no install needed

Add to `claude_desktop_config.json` (`%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "Luther Bible": {
      "url": "https://aifreund-luther-bible.hf.space/sse"
    }
  }
}
```

Restart Claude Desktop. Done. No API key, no local install.

> **Note:** The free HuggingFace tier may sleep after ~48h of inactivity. First request after wake takes ~15s; subsequent requests are ~50ms.

---

## Local setup (for development or offline use)

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Get the ChromaDB (choose one)

#### Option A — Download pre-built (~700 MB)

```bash
set CHROMA_PATH=C:\Projects\luther-mcp\bible_chroma_db
python -m luther_mcp download
```

#### Option B — Build from scratch (~10 minutes)

Clone the Bible data:
```bash
cd C:\Projects
git clone --depth 1 --filter=blob:none --sparse https://github.com/scrollmapper/bible_databases
cd bible_databases
git sparse-checkout set "formats/sqlite/GerBoLut.db" "formats/sqlite/KJV.db" "formats/sqlite/NHEB.db"
git checkout
```

Run the indexer:
```bash
cd C:\Projects\luther-mcp
python -m luther_mcp index
```

### 3. Add to Claude Desktop

Edit `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "Luther Bible": {
      "command": "C:\\Python313\\python.exe",
      "args": ["-m", "luther_mcp"],
      "cwd": "C:\\Projects\\luther-mcp",
      "env": {
        "CHROMA_PATH": "C:\\Projects\\luther-mcp\\bible_chroma_db",
        "PYTHONPATH": "C:\\Projects\\luther-mcp"
      }
    }
  }
}
```

`PYTHONPATH` is required — Claude Desktop does not add `cwd` to Python's module search path automatically.

---

## Available tools

### `search_bible`
Semantic search — finds verses by meaning, not keyword.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `query` | string | required | Query in any language |
| `translation` | string | `"GerBoLut"` | `"GerBoLut"` / `"KJV"` / `"web"` / `"all"` |
| `n_results` | integer | `10` | Results to return (max 50) |
| `testament` | string | — | `"OT"` or `"NT"` to filter |

### `get_verse`
Exact reference lookup by book/chapter/verse.

| Parameter | Type | Default | Description |
|---|---|---|---|
| `book` | string | required | German or English book name |
| `chapter` | integer | required | Chapter number |
| `verse` | integer | required | Verse number |
| `translation` | string | `"GerBoLut"` | `"GerBoLut"` / `"KJV"` / `"web"` / `"all"` |

### `list_translations`
Returns available translations with language, description, and verse count.

---

## Example queries

- `"Gottes Liebe zur Welt"` → 1. Johannes 4:9, Johannes 3:16, ...
- `"God so loved the world"` → Johannes 3:16 (cross-lingual)
- `"blessed are the peacemakers"` → Matthäus 5:9
- `"the Lord is my shepherd"` → Psalmen 23:1
- `get_verse("John", 3, 16, translation="all")` → all three translations

---

## Translations

| ID | Language | Description |
|---|---|---|
| `GerBoLut` | German | Luther Bible 1545 (modern spelling) |
| `KJV` | English | King James Version |
| `web` | English | New Heart English Bible |

Data sourced from [scrollmapper/bible_databases](https://github.com/scrollmapper/bible_databases).

---

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

Deployments to HuggingFace Spaces are triggered automatically via GitHub Actions on push to `main`. The Docker image is self-contained — the index is built into the image at build time.

---

## Publishing a release

To publish a pre-built ChromaDB to GitHub Releases (for `python -m luther_mcp download`):

```bash
set GITHUB_TOKEN=ghp_your_token_here
python scripts/create_release.py
```

Bump `__version__` in `luther_mcp/__init__.py` before running. The tag and download URL are derived automatically.

Data sourced from [scrollmapper/bible_databases](https://github.com/scrollmapper/bible_databases).