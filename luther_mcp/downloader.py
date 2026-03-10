"""
downloader.py — Downloads pre-built ChromaDB from GitHub Releases.

Usage:
    python -m luther_mcp download [--force]
"""

import os
import shutil
import sys
import tarfile
import urllib.request
from pathlib import Path

RELEASE_URL = (
    "https://github.com/happyherp/luther-mcp/releases/download/"
    "v0.2.0/bible_chroma_db.tar.gz"
)


def main():
    force = "--force" in sys.argv

    chroma_path = os.environ.get("CHROMA_PATH", "./bible_chroma_db")
    dest = Path(chroma_path)

    if dest.exists():
        if not force:
            print(f"ChromaDB already exists at {dest.resolve()}.")
            print("Use --force to overwrite.")
            return
        print(f"Removing existing ChromaDB at {dest.resolve()} ...")
        shutil.rmtree(dest)

    archive = dest.parent / "bible_chroma_db.tar.gz"

    print(f"Downloading pre-built ChromaDB (~700 MB) ...")
    print(f"Source: {RELEASE_URL}")

    def _progress(count, block_size, total_size):
        if total_size > 0:
            pct = min(count * block_size * 100 // total_size, 100)
            mb_done = count * block_size / 1_048_576
            mb_total = total_size / 1_048_576
            print(f"\r  {pct}%  ({mb_done:.0f} / {mb_total:.0f} MB)", end="", flush=True)

    try:
        urllib.request.urlretrieve(RELEASE_URL, archive, reporthook=_progress)
    except Exception as e:
        print(f"\nDownload failed: {e}", file=sys.stderr)
        if archive.exists():
            archive.unlink()
        sys.exit(1)

    print(f"\nExtracting to {dest.parent.resolve()} ...")
    with tarfile.open(archive, "r:gz") as tar:
        tar.extractall(dest.parent)

    archive.unlink()
    print(f"Done. ChromaDB is at: {dest.resolve()}")
    print("You can now start the server: python -m luther_mcp")
