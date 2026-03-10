"""
index_bible.py — Build ChromaDB vector index from Bible SQLite files.

Usage:
    python index_bible.py [--force]

Environment variables:
    OPENAI_API_KEY   Required
    BIBLE_DB_PATH    Path to scrollmapper formats/sqlite/ directory
                     (default: ../bible_databases/formats/sqlite relative to this script)
    CHROMA_PATH      Where to store ChromaDB (default: ./bible_chroma_db)
"""

import argparse
import os
import sqlite3
import sys
from pathlib import Path

import chromadb
from openai import OpenAI

# ---------------------------------------------------------------------------
# Book name mapping
# ---------------------------------------------------------------------------

BOOK_NAMES_EN = [
    "", # 1-indexed
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy",
    "Joshua", "Judges", "Ruth", "1 Samuel", "2 Samuel",
    "1 Kings", "2 Kings", "1 Chronicles", "2 Chronicles", "Ezra",
    "Nehemiah", "Esther", "Job", "Psalms", "Proverbs",
    "Ecclesiastes", "Song of Solomon", "Isaiah", "Jeremiah", "Lamentations",
    "Ezekiel", "Daniel", "Hosea", "Joel", "Amos",
    "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk",
    "Zephaniah", "Haggai", "Zechariah", "Malachi",
    # NT
    "Matthew", "Mark", "Luke", "John", "Acts",
    "Romans", "1 Corinthians", "2 Corinthians", "Galatians", "Ephesians",
    "Philippians", "Colossians", "1 Thessalonians", "2 Thessalonians", "1 Timothy",
    "2 Timothy", "Titus", "Philemon", "Hebrews", "James",
    "1 Peter", "2 Peter", "1 John", "2 John", "3 John",
    "Jude", "Revelation",
]

BOOK_NAMES_DE = [
    "", # 1-indexed
    "1. Mose", "2. Mose", "3. Mose", "4. Mose", "5. Mose",
    "Josua", "Richter", "Ruth", "1. Samuel", "2. Samuel",
    "1. Könige", "2. Könige", "1. Chronik", "2. Chronik", "Esra",
    "Nehemia", "Esther", "Hiob", "Psalmen", "Sprüche",
    "Prediger", "Hoheslied", "Jesaja", "Jeremia", "Klagelieder",
    "Hesekiel", "Daniel", "Hosea", "Joel", "Amos",
    "Obadja", "Jona", "Micha", "Nahum", "Habakuk",
    "Zefanja", "Haggai", "Sacharja", "Maleachi",
    # NT
    "Matthäus", "Markus", "Lukas", "Johannes", "Apostelgeschichte",
    "Römer", "1. Korinther", "2. Korinther", "Galater", "Epheser",
    "Philipper", "Kolosser", "1. Thessalonicher", "2. Thessalonicher", "1. Timotheus",
    "2. Timotheus", "Titus", "Philemon", "Hebräer", "Jakobus",
    "1. Petrus", "2. Petrus", "1. Johannes", "2. Johannes", "3. Johannes",
    "Judas", "Offenbarung",
]

# Translations to index: (collection_name, db_filename, use_german_names)
# Files live under formats/sqlite/ in the scrollmapper/bible_databases repo.
# "web" collection uses NHEB.db (New Heart English Bible, based on World English Bible).
TRANSLATIONS = [
    ("GerBoLut", "GerBoLut.db", True),
    ("KJV",      "KJV.db",      False),
    ("web",      "NHEB.db",     False),
]

BATCH_SIZE = 2048


def get_testament(book_number: int) -> str:
    return "OT" if book_number <= 39 else "NT"


def load_verses(db_path: Path, collection_name: str) -> list[dict]:
    """Load all verses from a Bible SQLite file.

    The scrollmapper repo uses translation-specific table names, e.g.:
      GerBoLut_verses (book_id, chapter, verse, text)
    The 'web' collection maps to NHEB.db, so its table is NHEB_verses.
    """
    # Map collection name -> actual table prefix in the .db file
    TABLE_PREFIX = {
        "GerBoLut": "GerBoLut",
        "KJV": "KJV",
        "web": "NHEB",  # NHEB.db is used for the 'web' collection
    }
    prefix = TABLE_PREFIX.get(collection_name, collection_name)
    table = f"{prefix}_verses"

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(f"SELECT book_id, chapter, verse, text FROM {table} ORDER BY book_id, chapter, verse")
    rows = cur.fetchall()
    conn.close()
    return [{"b": r[0], "c": r[1], "v": r[2], "t": r[3].strip()} for r in rows]


def build_document(book_name: str, chapter: int, verse: int, text: str) -> str:
    return f"{book_name} {chapter}:{verse} — {text}"


def embed_batch(client: OpenAI, texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=texts,
    )
    return [item.embedding for item in response.data]


def index_translation(
    collection_name: str,
    db_path: Path,
    use_german_names: bool,
    chroma_client: chromadb.PersistentClient,
    openai_client: OpenAI,
    force: bool,
) -> None:
    # Check if already indexed
    existing = [c.name for c in chroma_client.list_collections()]
    if collection_name in existing:
        if force:
            print(f"[{collection_name}] Force flag set — deleting existing collection.")
            chroma_client.delete_collection(collection_name)
        else:
            print(f"[{collection_name}] Already indexed. Use --force to re-index. Skipping.")
            return

    if not db_path.exists():
        print(f"[{collection_name}] SQLite file not found: {db_path}. Skipping.", file=sys.stderr)
        return

    collection = chroma_client.create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"},
    )

    verses = load_verses(db_path, collection_name)
    total = len(verses)
    print(f"[{collection_name}] {total} verses loaded. Starting embedding...")

    # Process in batches
    for batch_start in range(0, total, BATCH_SIZE):
        batch = verses[batch_start : batch_start + BATCH_SIZE]

        ids = []
        documents = []
        metadatas = []

        for v in batch:
            b, c, verse_num, text = v["b"], v["c"], v["v"], v["t"]
            book_en = BOOK_NAMES_EN[b] if b < len(BOOK_NAMES_EN) else f"Book{b}"
            book_de = BOOK_NAMES_DE[b] if b < len(BOOK_NAMES_DE) else f"Buch{b}"
            book_name = book_de if use_german_names else book_en

            doc = build_document(book_name, c, verse_num, text)
            doc_id = f"{collection_name}_{b}_{c}_{verse_num}"

            ids.append(doc_id)
            documents.append(doc)
            metadatas.append({
                "book": book_name,
                "book_en": book_en,
                "book_number": b,
                "chapter": c,
                "verse": verse_num,
                "translation": collection_name,
                "testament": get_testament(b),
            })

        embeddings = embed_batch(openai_client, documents)
        collection.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)

        done = min(batch_start + BATCH_SIZE, total)
        print(f"[{collection_name}] {done}/{total} verses indexed")

    print(f"[{collection_name}] Done.")


def main():
    parser = argparse.ArgumentParser(description="Index Bible translations into ChromaDB.")
    parser.add_argument("--force", action="store_true", help="Re-index even if collection already exists.")
    args = parser.parse_args()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)

    bible_db_path = os.environ.get(
        "BIBLE_DB_PATH",
        str(Path(__file__).parent.parent / "bible_databases" / "formats" / "sqlite"),
    )

    chroma_path = os.environ.get("CHROMA_PATH", "./bible_chroma_db")

    bible_db_dir = Path(bible_db_path)
    chroma_dir = Path(chroma_path)
    chroma_dir.mkdir(parents=True, exist_ok=True)

    openai_client = OpenAI(api_key=api_key)
    chroma_client = chromadb.PersistentClient(path=str(chroma_dir))

    for collection_name, sqlite_filename, use_german_names in TRANSLATIONS:
        db_path = bible_db_dir / sqlite_filename
        index_translation(
            collection_name=collection_name,
            db_path=db_path,
            use_german_names=use_german_names,
            chroma_client=chroma_client,
            openai_client=openai_client,
            force=args.force,
        )

    print("\nAll done. ChromaDB is at:", chroma_dir.resolve())


if __name__ == "__main__":
    main()
