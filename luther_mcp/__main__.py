"""
__main__.py — Entry point for `python -m luther_mcp`.

Usage:
    python -m luther_mcp                    # start MCP server (default)
    python -m luther_mcp serve              # start MCP server (explicit)
    python -m luther_mcp index [--force]    # run the indexer
    python -m luther_mcp download [--force] # download pre-built ChromaDB
"""

import sys


def main():
    args = sys.argv[1:]

    if not args or args[0] == "serve":
        import asyncio
        from luther_mcp.server import main as run
        asyncio.run(run())

    elif args[0] == "index":
        sys.argv = [sys.argv[0]] + args[1:]
        from luther_mcp.indexer import main as run
        run()

    elif args[0] == "download":
        sys.argv = [sys.argv[0]] + args[1:]
        from luther_mcp.downloader import main as run
        run()

    else:
        print(
            f"Unknown subcommand: {args[0]}\n"
            "Usage: python -m luther_mcp [serve|index [--force]|download [--force]]",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
