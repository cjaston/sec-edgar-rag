"""
Embedding generation for SEC filing chunks.

Uses OpenAI's text-embedding-3-small by default (configurable). Processes chunks
in batches to stay within API rate limits and minimize cost.

Cost context (text-embedding-3-small, March 2026):
  - ~$0.02 per 1M tokens
  - Our corpus (~15K chunks, ~17M tokens) ≈ $0.34
  - Full re-embedding costs under a dollar

The embedding model is configurable via EMBEDDING_MODEL env var. If a client
needs higher recall, switch to text-embedding-3-large (5x cost, ~2% better recall
at this scale).
"""

import time

from openai import OpenAI

import config

# Reuse a single client instance per API key to avoid connection overhead
_clients: dict[str, OpenAI] = {}


def _get_client(api_key: str | None = None) -> OpenAI:
    """Get or create an OpenAI client for the given API key."""
    key = api_key or config.OPENAI_API_KEY
    if key not in _clients:
        _clients[key] = OpenAI(api_key=key)
    return _clients[key]


def get_embeddings(texts: list[str], model: str | None = None, api_key: str | None = None) -> list[list[float]]:
    """
    Generate embeddings for a list of texts using OpenAI's API.

    Args:
        texts: List of text strings to embed.
        model: Embedding model name. Defaults to config.EMBEDDING_MODEL.
        api_key: OpenAI API key. Defaults to config.OPENAI_API_KEY.

    Returns:
        List of embedding vectors (list of floats), one per input text.
    """
    model = model or config.EMBEDDING_MODEL
    client = _get_client(api_key)
    all_embeddings = []
    batch_size = config.EMBEDDING_BATCH_SIZE

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]

        # Retry with exponential backoff on rate limits
        response = None
        for attempt in range(5):
            try:
                response = client.embeddings.create(
                    model=model,
                    input=batch,
                )
                break
            except Exception as e:
                if "rate_limit" in str(e).lower() or "429" in str(e):
                    wait = 2 ** attempt
                    print(f"    Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    if attempt == 4:
                        raise  # Give up after 5 attempts
                else:
                    raise

        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)

        # Pause between batches to respect rate limits
        if i + batch_size < len(texts):
            time.sleep(0.5)

    return all_embeddings


def embed_query(query: str, model: str | None = None, api_key: str | None = None) -> list[float]:
    """
    Generate an embedding for a single query string.

    Separated from batch embedding because query embedding happens at query time
    (latency-sensitive) while chunk embedding happens at index time (throughput-sensitive).
    """
    result = get_embeddings([query], model=model, api_key=api_key)
    return result[0]
