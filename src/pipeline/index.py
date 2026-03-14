"""
ChromaDB vector index management for SEC filing chunks.

Handles building, persisting, and loading the vector store. ChromaDB stores
embeddings alongside metadata, enabling the filter-first retrieval pattern:
metadata filters (ticker, sector, date) are applied BEFORE semantic search,
so irrelevant chunks never enter the similarity calculation.

Embedding optimization:
  Every chunk is indexed with its full metadata (zero data loss), but identical
  text across filings is only embedded ONCE via an embedding cache. If 16 AAPL
  filings all contain "Mine Safety Disclosures: Not applicable", we make one
  API call and reuse the vector for all 16 index entries. This cuts embedding
  cost proportional to the duplicate rate without losing any queryable data.

Why ChromaDB:
  - Runs locally, zero external dependencies
  - Native metadata filtering with $and/$or operators
  - Persists to disk — ship pre-built index with the repo
  - Cosine similarity built-in
  - No API keys, no hosted service, no network dependency at query time
"""

import hashlib

import chromadb

import config
from src.pipeline.embeddings import get_embeddings


def _clean_metadata(meta: dict) -> dict:
    """Ensure all metadata values are ChromaDB-compatible types."""
    clean = {}
    for k, v in meta.items():
        if v is None:
            clean[k] = ""
        elif isinstance(v, (str, int, float, bool)):
            clean[k] = v
        else:
            clean[k] = str(v)
    return clean


def get_collection(chroma_dir: str | None = None) -> chromadb.Collection:
    """
    Get or create the ChromaDB collection.

    Uses persistent storage so the index survives between runs.
    The collection is created with cosine similarity distance.
    """
    path = str(chroma_dir or config.CHROMA_DIR)
    client = chromadb.PersistentClient(path=path)
    collection = client.get_or_create_collection(
        name=config.CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )
    return collection


def build_index(chunks: list[dict], chroma_dir: str | None = None) -> chromadb.Collection:
    """
    Build the ChromaDB index from chunked filing data.

    Uses an embedding cache keyed by text hash: identical text across different
    filings is embedded once and the vector is reused. Every chunk is still
    added to the index with its own unique ID and metadata — zero data loss.

    Args:
        chunks: List of chunk dicts from chunker.chunk_corpus().
        chroma_dir: Override for ChromaDB storage path.

    Returns:
        The populated ChromaDB collection.
    """
    collection = get_collection(chroma_dir)

    # Clear existing data for clean rebuild
    existing = collection.count()
    if existing > 0:
        print(f"  Collection already has {existing} documents. Clearing for rebuild...")
        path = str(chroma_dir or config.CHROMA_DIR)
        client = chromadb.PersistentClient(path=path)
        client.delete_collection(config.CHROMA_COLLECTION)
        collection = client.get_or_create_collection(
            name=config.CHROMA_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    # Build embedding cache: hash → vector
    # This is the core optimization — identical text is embedded once
    embedding_cache: dict[str, list[float]] = {}
    total = len(chunks)
    batch_size = config.EMBEDDING_BATCH_SIZE

    # First pass: identify unique texts that need embedding
    chunk_hashes = []
    unique_texts = {}  # hash → text (preserves insertion order)
    for chunk in chunks:
        text_hash = hashlib.md5(chunk["text"].encode()).hexdigest()
        chunk_hashes.append(text_hash)
        if text_hash not in unique_texts:
            unique_texts[text_hash] = chunk["text"]

    unique_count = len(unique_texts)
    duplicate_count = total - unique_count
    print(f"Building index: {total} chunks, {unique_count} unique texts, {duplicate_count} duplicates skipped for embedding")

    # Embed only unique texts
    unique_hash_list = list(unique_texts.keys())
    unique_text_list = list(unique_texts.values())

    for i in range(0, len(unique_text_list), batch_size):
        batch_texts = unique_text_list[i:i + batch_size]
        batch_hashes = unique_hash_list[i:i + batch_size]

        embeddings = get_embeddings(batch_texts)

        for h, emb in zip(batch_hashes, embeddings):
            embedding_cache[h] = emb

        processed = min(i + batch_size, len(unique_text_list))
        if processed % 500 == 0 or processed == len(unique_text_list):
            print(f"  Embedded {processed}/{unique_count} unique texts...")

    # Second pass: add ALL chunks to ChromaDB with cached embeddings
    print(f"  Adding {total} chunks to index...")
    for i in range(0, total, batch_size):
        batch = chunks[i:i + batch_size]
        batch_hashes_slice = chunk_hashes[i:i + batch_size]

        batch_ids = [c["chunk_id"] for c in batch]
        batch_texts = [c["text"] for c in batch]
        batch_embeddings = [embedding_cache[h] for h in batch_hashes_slice]
        batch_metadata = [_clean_metadata(c["metadata"]) for c in batch]

        collection.add(
            ids=batch_ids,
            embeddings=batch_embeddings,
            documents=batch_texts,
            metadatas=batch_metadata,
        )

        processed = min(i + batch_size, total)
        if processed % 2000 == 0 or processed == total:
            print(f"  Indexed {processed}/{total} chunks...")

    print(f"  Done: {collection.count()} documents in index")
    print(f"  Embedding API calls saved: {duplicate_count} (reused cached vectors)")
    return collection


def load_index(chroma_dir: str | None = None) -> chromadb.Collection:
    """
    Load an existing ChromaDB index from disk.

    Returns the collection if it exists and has data.
    Raises ValueError if the index is empty or doesn't exist.

    IMPORTANT: When querying, always use query_embeddings (from embed_query())
    instead of query_texts. ChromaDB's built-in embedding model (384 dims)
    is different from our OpenAI embeddings (1536 dims).
    """
    collection = get_collection(chroma_dir)
    count = collection.count()
    if count == 0:
        raise ValueError(
            f"Index at {chroma_dir or config.CHROMA_DIR} is empty. "
            "Run 'python scripts/build_index.py' to build it."
        )
    return collection
