"""
bible_mcp_server.py — MCP server exposing semantic Bible search.

Communicates over stdio (as required by Claude Desktop).

Environment variables:
    OPENAI_API_KEY   Required
    CHROMA_PATH      Path to ChromaDB built by index_bible.py
"""

import os
import sys
from pathlib import Path
from typing import Any

import chromadb
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from openai import OpenAI

# ---------------------------------------------------------------------------
# Book name mapping (shared with indexer)
# ---------------------------------------------------------------------------

BOOK_NAMES_EN = [
    "",
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy",
    "Joshua", "Judges", "Ruth", "1 Samuel", "2 Samuel",
    "1 Kings", "2 Kings", "1 Chronicles", "2 Chronicles", "Ezra",
    "Nehemiah", "Esther", "Job", "Psalms", "Proverbs",
    "Ecclesiastes", "Song of Solomon", "Isaiah", "Jeremiah", "Lamentations",
    "Ezekiel", "Daniel", "Hosea", "Joel", "Amos",
    "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk",
    "Zephaniah", "Haggai", "Zechariah", "Malachi",
    "Matthew", "Mark", "Luke", "John", "Acts",
    "Romans", "1 Corinthians", "2 Corinthians", "Galatians", "Ephesians",
    "Philippians", "Colossians", "1 Thessalonians", "2 Thessalonians", "1 Timothy",
    "2 Timothy", "Titus", "Philemon", "Hebrews", "James",
    "1 Peter", "2 Peter", "1 John", "2 John", "3 John",
    "Jude", "Revelation",
]

BOOK_NAMES_DE = [
    "",
    "1. Mose", "2. Mose", "3. Mose", "4. Mose", "5. Mose",
    "Josua", "Richter", "Ruth", "1. Samuel", "2. Samuel",
    "1. Könige", "2. Könige", "1. Chronik", "2. Chronik", "Esra",
    "Nehemia", "Esther", "Hiob", "Psalmen", "Sprüche",
    "Prediger", "Hoheslied", "Jesaja", "Jeremia", "Klagelieder",
    "Hesekiel", "Daniel", "Hosea", "Joel", "Amos",
    "Obadja", "Jona", "Micha", "Nahum", "Habakuk",
    "Zefanja", "Haggai", "Sacharja", "Maleachi",
    "Matthäus", "Markus", "Lukas", "Johannes", "Apostelgeschichte",
    "Römer", "1. Korinther", "2. Korinther", "Galater", "Epheser",
    "Philipper", "Kolosser", "1. Thessalonicher", "2. Thessalonicher", "1. Timotheus",
    "2. Timotheus", "Titus", "Philemon", "Hebräer", "Jakobus",
    "1. Petrus", "2. Petrus", "1. Johannes", "2. Johannes", "3. Johannes",
    "Judas", "Offenbarung",
]

# Build lookup: lowercase name -> book number
_BOOK_LOOKUP: dict[str, int] = {}
for _i, _name in enumerate(BOOK_NAMES_EN):
    if _name:
        _BOOK_LOOKUP[_name.lower()] = _i
for _i, _name in enumerate(BOOK_NAMES_DE):
    if _name:
        _BOOK_LOOKUP[_name.lower()] = _i

TRANSLATION_META = {
    "GerBoLut": {
        "language": "German",
        "description": "Luther Bible 1545 (modern spelling)",
    },
    "KJV": {
        "language": "English",
        "description": "King James Version",
    },
    "web": {
        "language": "English",
        "description": "World English Bible",
    },
}

ALL_TRANSLATIONS = list(TRANSLATION_META.keys())


def resolve_book_number(book: str) -> int | None:
    """Resolve German or English book name (case-insensitive) to book number."""
    return _BOOK_LOOKUP.get(book.strip().lower())


def score_from_distance(distance: float) -> float:
    """Convert cosine distance to similarity score [0, 1]."""
    return round(max(0.0, 1.0 - distance), 4)


# ---------------------------------------------------------------------------
# Server state (initialized once at startup)
# ---------------------------------------------------------------------------

_openai_client: OpenAI | None = None
_chroma_client: chromadb.PersistentClient | None = None


def get_collection(name: str) -> chromadb.Collection | None:
    try:
        return _chroma_client.get_collection(name)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def tool_search_bible(
    query: str,
    translation: str = "GerBoLut",
    n_results: int = 10,
    testament: str | None = None,
) -> list[dict]:
    embedding_response = _openai_client.embeddings.create(
        model="text-embedding-3-small",
        input=[query],
    )
    query_embedding = embedding_response.data[0].embedding

    where_filter = {"testament": testament} if testament in ("OT", "NT") else None

    translations_to_search = ALL_TRANSLATIONS if translation == "all" else [translation]
    raw_results: list[dict] = []

    for tname in translations_to_search:
        col = get_collection(tname)
        if col is None:
            continue
        kwargs: dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": n_results,
            "include": ["documents", "metadatas", "distances"],
        }
        if where_filter:
            kwargs["where"] = where_filter
        try:
            results = col.query(**kwargs)
        except Exception:
            continue

        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            raw_results.append({
                "reference": f"{meta['book']} {meta['chapter']}:{meta['verse']}",
                "reference_en": f"{meta['book_en']} {meta['chapter']}:{meta['verse']}",
                "text": meta.get("text", doc.split(" — ", 1)[-1]),
                "translation": meta["translation"],
                "score": score_from_distance(dist),
                "_canon_key": f"{meta['book_number']}_{meta['chapter']}_{meta['verse']}",
                "_doc": doc,
            })

    if translation == "all":
        # Deduplicate: keep best score per canonical reference
        best: dict[str, dict] = {}
        for r in raw_results:
            key = r["_canon_key"]
            if key not in best or r["score"] > best[key]["score"]:
                best[key] = r
        raw_results = sorted(best.values(), key=lambda x: x["score"], reverse=True)[:n_results]
    else:
        raw_results.sort(key=lambda x: x["score"], reverse=True)

    # Strip internal keys
    return [
        {k: v for k, v in r.items() if not k.startswith("_")}
        for r in raw_results
    ]


def tool_get_verse(
    book: str,
    chapter: int,
    verse: int,
    translation: str = "GerBoLut",
) -> dict | list[dict]:
    book_number = resolve_book_number(book)
    if book_number is None:
        return {"error": f"Unknown book name: '{book}'"}

    translations_to_query = ALL_TRANSLATIONS if translation == "all" else [translation]
    results = []

    for tname in translations_to_query:
        col = get_collection(tname)
        if col is None:
            continue
        doc_id = f"{tname}_{book_number}_{chapter}_{verse}"
        try:
            res = col.get(ids=[doc_id], include=["documents", "metadatas"])
        except Exception:
            continue
        if not res["ids"]:
            continue
        meta = res["metadatas"][0]
        doc = res["documents"][0]
        text = doc.split(" — ", 1)[-1] if " — " in doc else doc
        results.append({
            "reference": f"{meta['book']} {chapter}:{verse}",
            "reference_en": f"{meta['book_en']} {chapter}:{verse}",
            "text": text,
            "translation": tname,
        })

    if translation != "all":
        return results[0] if results else {"error": f"Verse not found: {book} {chapter}:{verse} in {translation}"}
    return results


def tool_list_translations() -> list[dict]:
    output = []
    for tname, meta in TRANSLATION_META.items():
        col = get_collection(tname)
        verse_count = col.count() if col else 0
        output.append({
            "id": tname,
            "language": meta["language"],
            "description": meta["description"],
            "verse_count": verse_count,
            "indexed": col is not None,
        })
    return output


# ---------------------------------------------------------------------------
# MCP server definition
# ---------------------------------------------------------------------------

server = Server("luther-bible")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_bible",
            description=(
                "Semantic search over the Bible. Supports German and English queries. "
                "Returns the most relevant verses by meaning, not just keyword match."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (any language — German or English both work)",
                    },
                    "translation": {
                        "type": "string",
                        "enum": ["GerBoLut", "KJV", "web", "all"],
                        "default": "GerBoLut",
                        "description": "Which translation to search. Use 'all' to search all and deduplicate.",
                    },
                    "n_results": {
                        "type": "integer",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                        "description": "Number of results to return.",
                    },
                    "testament": {
                        "type": "string",
                        "enum": ["OT", "NT"],
                        "description": "Optional filter: 'OT' (Old Testament) or 'NT' (New Testament).",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_verse",
            description=(
                "Retrieve an exact Bible verse by reference. "
                "Accepts German or English book names (case-insensitive)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "book": {
                        "type": "string",
                        "description": "Book name in German or English, e.g. 'Johannes' or 'John'.",
                    },
                    "chapter": {
                        "type": "integer",
                        "description": "Chapter number.",
                    },
                    "verse": {
                        "type": "integer",
                        "description": "Verse number.",
                    },
                    "translation": {
                        "type": "string",
                        "enum": ["GerBoLut", "KJV", "web", "all"],
                        "default": "GerBoLut",
                        "description": "Translation. Use 'all' to get the verse from every available translation.",
                    },
                },
                "required": ["book", "chapter", "verse"],
            },
        ),
        Tool(
            name="list_translations",
            description="List available Bible translations with metadata and verse counts.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    import json

    if name == "search_bible":
        result = tool_search_bible(
            query=arguments["query"],
            translation=arguments.get("translation", "GerBoLut"),
            n_results=arguments.get("n_results", 10),
            testament=arguments.get("testament"),
        )
    elif name == "get_verse":
        result = tool_get_verse(
            book=arguments["book"],
            chapter=int(arguments["chapter"]),
            verse=int(arguments["verse"]),
            translation=arguments.get("translation", "GerBoLut"),
        )
    elif name == "list_translations":
        result = tool_list_translations()
    else:
        result = {"error": f"Unknown tool: {name}"}

    return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    global _openai_client, _chroma_client

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not set.", file=sys.stderr)
        sys.exit(1)

    chroma_path = os.environ.get("CHROMA_PATH", "./bible_chroma_db")
    chroma_dir = Path(chroma_path)
    if not chroma_dir.exists():
        print(f"Error: CHROMA_PATH '{chroma_dir}' does not exist. Run index_bible.py first.", file=sys.stderr)
        sys.exit(1)

    _openai_client = OpenAI(api_key=api_key)
    _chroma_client = chromadb.PersistentClient(path=str(chroma_dir))

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
