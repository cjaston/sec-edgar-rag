#!/usr/bin/env python3
"""
One-shot index builder: preprocess → chunk → embed → index.

Run this once to build the ChromaDB vector index from the raw SEC filings.
The index persists to disk at ./chroma_db/ and ships with the repo so
reviewers don't need to re-run this step.

Usage:
    source venv/bin/activate
    python scripts/build_index.py
"""

import sys
import time
from pathlib import Path

# Add project root to path so imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from src.pipeline.preprocess import parse_corpus
from src.pipeline.chunker import chunk_corpus
from src.utils.sector_lookup import resolve_sectors
from src.pipeline.index import build_index


def main():
    start = time.time()

    print("=" * 60)
    print("SEC Filing Research Tool — Index Builder")
    print("=" * 60)

    # Step 1: Preprocess filings
    print("\n[1/4] Preprocessing filings...")
    filings = parse_corpus()

    # Step 2: Resolve sectors for all companies
    print("\n[2/4] Resolving company sectors from SEC EDGAR...")
    tickers = list(set(f.metadata.ticker for f in filings))
    sector_map = resolve_sectors(tickers)
    print(f"  Resolved {len(sector_map)} companies across {len(set(sector_map.values()))} sectors")

    # Step 3: Chunk all filings
    print("\n[3/4] Chunking filings...")
    chunks = chunk_corpus(filings)

    # Step 4: Embed and index
    print("\n[4/4] Embedding and indexing...")
    collection = build_index(chunks)

    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"Index build complete in {elapsed:.1f}s")
    print(f"  {len(filings)} filings → {sum(len(f.sections) for f in filings)} sections → {len(chunks)} chunks")
    print(f"  Index stored at: {config.CHROMA_DIR}")
    print(f"  Collection: {config.CHROMA_COLLECTION} ({collection.count()} documents)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
