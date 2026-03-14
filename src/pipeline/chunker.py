"""
Section-aware text chunking for SEC filings.

Splits each section into chunks of configurable size (in tokens, not characters)
with overlap for context continuity. Each chunk inherits its parent section's
metadata — this is what enables the filter-first retrieval pattern.

Why token-based, not character-based:
  - LLM context windows and embedding models operate on tokens
  - A 1500-token chunk maps predictably to embedding model capacity
  - Character-based splitting would produce inconsistent token counts
    (financial text with numbers/symbols tokenizes differently than prose)

Why section-aware:
  - A chunk should never span two sections (e.g., half Risk Factors, half MD&A)
  - Section boundaries are natural topic boundaries in SEC filings
  - Each chunk's metadata (section_name, item_number) stays accurate
"""

import hashlib

import tiktoken

import config
from src.pipeline.preprocess import ParsedFiling, Section
from src.utils.sector_lookup import get_sector


# Initialize tokenizer once at module level — this is a pure function with no side effects
_encoder = tiktoken.encoding_for_model("gpt-4o")


def count_tokens(text: str) -> int:
    """Count tokens in text using the GPT-4o tokenizer."""
    return len(_encoder.encode(text))


def _split_section_into_chunks(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """
    Split text into token-sized chunks with overlap.

    Uses sentence boundaries where possible to avoid cutting mid-sentence.
    The step size is always (chunk_size - overlap) to ensure consistent
    forward progress and predictable chunk counts.
    """
    tokens = _encoder.encode(text)
    if len(tokens) <= chunk_size:
        return [text]

    chunks = []
    step = chunk_size - chunk_overlap
    start = 0

    while start < len(tokens):
        end = min(start + chunk_size, len(tokens))
        chunk_text = _encoder.decode(tokens[start:end])

        # Try to end at a sentence boundary for cleaner chunks
        # Only look in the last 20% of the chunk to avoid making it too short
        if end < len(tokens):
            search_zone = chunk_text[len(chunk_text) * 4 // 5:]
            for sep in [". ", "? ", "! ", "\n"]:
                break_pos = search_zone.rfind(sep)
                if break_pos != -1:
                    # Calculate absolute position in chunk_text
                    abs_pos = len(chunk_text) * 4 // 5 + break_pos + len(sep)
                    chunk_text = chunk_text[:abs_pos].strip()
                    break

        if chunk_text:
            chunks.append(chunk_text)

        start += step

    return chunks


def _deduplicate_sections(sections: list) -> list:
    """
    Deduplicate and merge sections within a single filing.

    The preprocessor's _normalize_text() can fragment a single section into
    multiple pieces when it splits at inline references like "see Item 1A".
    Rather than keeping only the longest fragment (which loses content), we
    merge all fragments with the same (Item number, Part) into one section.

    Strategy:
    1. Exact dedup by source_hash — skip identical text
    2. Merge by (Item number, Part) — concatenate all fragments in order
    """
    # Exact dedup: skip sections with identical content
    seen_hashes = set()
    unique_sections = []
    for section in sections:
        if section.source_hash in seen_hashes:
            continue
        seen_hashes.add(section.source_hash)
        unique_sections.append(section)

    # Merge sections with the same (Item number, Part) — preserves all content
    # while eliminating the fragmentation caused by _normalize_text()
    by_item_part: dict[tuple, list] = {}
    for section in unique_sections:
        key = (section.item_number, section.part)
        if key not in by_item_part:
            by_item_part[key] = []
        by_item_part[key].append(section)

    merged = []
    for (item_num, part), fragments in by_item_part.items():
        if len(fragments) == 1:
            merged.append(fragments[0])
        else:
            # Concatenate fragments in their original order (order preserved from parsing)
            # Use the name from the longest fragment (most likely the real section heading)
            best_name = max(fragments, key=lambda s: len(s.text)).name
            combined_text = "\n\n".join(s.text for s in fragments)
            merged.append(Section(
                name=best_name,
                item_number=item_num,
                text=combined_text,
                part=part,
                source_hash=hashlib.sha256(combined_text.encode()).hexdigest(),
            ))

    return merged


def chunk_filing(filing: ParsedFiling) -> list[dict]:
    """
    Chunk a single parsed filing into index-ready records.

    Each chunk is a dict with:
      - chunk_id: Unique identifier
      - text: The chunk content
      - metadata: All fields needed for filtering and citation

    Returns:
        List of chunk dicts ready for embedding and indexing.
    """
    chunks = []
    ticker = filing.metadata.ticker
    filing_type = filing.metadata.filing_type
    filing_date = filing.metadata.filing_date

    # Deduplicate sections before chunking
    sections = _deduplicate_sections(filing.sections)

    # Resolve sector once per filing, not per chunk
    sector = get_sector(ticker)

    for section_idx, section in enumerate(sections):
        section_chunks = _split_section_into_chunks(
            section.text,
            config.CHUNK_SIZE,
            config.CHUNK_OVERLAP,
        )

        # Filter out chunks below minimum token threshold
        valid_chunks = [
            (i, text) for i, text in enumerate(section_chunks)
            if count_tokens(text) >= config.MIN_CHUNK_TOKENS
        ]

        for chunk_idx, (original_idx, chunk_text) in enumerate(valid_chunks):
            # Build a deterministic, human-readable chunk ID
            # Include section_index to handle duplicate Item numbers
            # (e.g., 10-Q has Item 1 in both Part I and Part II)
            chunk_id = (
                f"{ticker}_{filing_type}_{filing_date}"
                f"_s{section_idx}_{section.item_number}_{chunk_idx}"
            )

            chunks.append({
                "chunk_id": chunk_id,
                "text": chunk_text,
                "metadata": {
                    # Filing identity
                    "ticker": ticker,
                    "company_name": filing.metadata.company_name,
                    "cik": filing.metadata.cik,
                    "filing_type": filing_type,
                    "filing_date": filing_date,
                    "report_period": filing.metadata.report_period,
                    "sector": sector,
                    # Section identity
                    "section_name": section.name,
                    "item_number": section.item_number,
                    "part": section.part,
                    # Chunk position
                    "chunk_index": chunk_idx,
                    "total_chunks": len(valid_chunks),
                    # Source traceability
                    "source_url": filing.metadata.source_url,
                    "source_file": filing.metadata.source_file,
                    "source_hash": section.source_hash,
                    "section_index": section_idx,
                    # Access control (populated with defaults, enforced by auth.py)
                    "tenant_id": config.DEFAULT_TENANT_ID,
                    "access_level": config.DEFAULT_ACCESS_LEVEL,
                },
            })

    return chunks


def chunk_corpus(filings: list[ParsedFiling]) -> list[dict]:
    """
    Chunk all filings in the corpus.

    Args:
        filings: List of ParsedFiling objects from the preprocessor.

    Returns:
        List of chunk dicts ready for embedding and indexing.
    """
    all_chunks = []

    print(f"Chunking {len(filings)} filings (chunk_size={config.CHUNK_SIZE}, overlap={config.CHUNK_OVERLAP})...")

    for i, filing in enumerate(filings):
        filing_chunks = chunk_filing(filing)
        all_chunks.extend(filing_chunks)
        if (i + 1) % 50 == 0:
            print(f"  Chunked {i + 1}/{len(filings)} filings ({len(all_chunks)} chunks so far)...")

    print(f"  Done: {len(all_chunks)} chunks from {len(filings)} filings")
    return all_chunks
