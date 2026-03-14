"""
Query parsing and metadata-filtered retrieval for SEC filings.

The retrieval pipeline:
  1. Parse the query — extract tickers, sectors, filing types, date hints
  2. Build metadata filters — combine query filters with access control
  3. Embed the query — single OpenAI API call
  4. Search ChromaDB — semantic similarity within the filtered set only
  5. Return ranked chunks with full metadata for citation

The filter-first pattern is critical: metadata filters are applied BEFORE
semantic search, so irrelevant chunks never enter the similarity calculation.
This is both faster and more accurate than searching everything and filtering after.
"""

import copy
import re

import config
from src.pipeline.embeddings import embed_query
from src.pipeline.index import load_index
from src.enterprise.auth import User, get_access_filter


# ── Ticker recognition ────────────────────────────────────────────────────────
# Built dynamically from the SIC cache so it adapts to any corpus

def _load_known_tickers() -> set[str]:
    """Load all tickers we know about from the SIC cache."""
    import json
    if config.SIC_CACHE_PATH.exists():
        with open(config.SIC_CACHE_PATH) as f:
            return set(json.load(f).keys())
    return set()


# Common company name → ticker mappings for natural language queries
_COMPANY_ALIASES = {
    "apple": "AAPL", "microsoft": "MSFT", "google": "GOOG", "alphabet": "GOOG",
    "amazon": "AMZN", "meta": "META", "facebook": "META", "nvidia": "NVDA",
    "tesla": "TSLA", "jpmorgan": "JPM", "jp morgan": "JPM", "chase": "JPM",
    "pfizer": "PFE", "exxon": "XOM", "exxonmobil": "XOM",
    "berkshire": "BRK", "johnson & johnson": "JNJ", "j&j": "JNJ",
    "coca-cola": "KO", "coke": "KO", "pepsi": "PEP", "pepsico": "PEP",
    "walmart": "WMT", "disney": "DIS", "netflix": "NFLX", "nike": "NKE",
    "boeing": "BA", "caterpillar": "CAT", "intel": "INTC",
    "visa": "V", "mastercard": "MA", "starbucks": "SBUX",
    "home depot": "HD", "target": "TGT", "costco": "COST",
    "oracle": "ORCL", "adobe": "ADBE", "salesforce": "CRM", "cisco": "CSCO",
    "ibm": "IBM", "amd": "AMD", "comcast": "CMCSA", "at&t": "T", "verizon": "VZ",
    "ups": "UPS", "lockheed": "LMT", "lockheed martin": "LMT",
    "raytheon": "RTX", "deere": "DE", "john deere": "DE",
    "ge": "GE", "general electric": "GE",
    "goldman": "GS", "goldman sachs": "GS", "morgan stanley": "MS",
    "bank of america": "BAC", "blackrock": "BLK", "american express": "AXP",
    "chevron": "CVX", "procter": "PG", "procter & gamble": "PG", "p&g": "PG",
    "eli lilly": "LLY", "lilly": "LLY", "merck": "MRK", "abbvie": "ABBV",
    "unitedhealth": "UNH", "thermo fisher": "TMO", "mcdonald": "MCD",
    "mcdonalds": "MCD", "mcdonald's": "MCD",
}

# Section name hints in natural language
_SECTION_HINTS = {
    "risk": "Risk Factors",
    "risks": "Risk Factors",
    "risk factor": "Risk Factors",
    "risk factors": "Risk Factors",
    "business": "Business",
    "overview": "Business",
    "revenue": "MD&A",
    "financial": "Financial Statements",
    "financials": "Financial Statements",
    "management discussion": "MD&A",
    "md&a": "MD&A",
    "mda": "MD&A",
    "cybersecurity": "Cybersecurity",
    "cyber": "Cybersecurity",
    "legal": "Legal Proceedings",
    "properties": "Properties",
    "compensation": "Executive Compensation",
    "market risk": "Market Risk Disclosures",
}


def parse_query(query: str) -> dict:
    """
    Extract structured filters from a natural language query.

    Returns a dict with optional keys:
      - tickers: list of matched tickers
      - sectors: list of matched sectors
      - section_hint: suggested section name
      - filing_type: "10-K" or "10-Q" if mentioned
      - years: list of year strings if mentioned

    This is heuristic — no API call needed. The semantic search handles
    the nuance; these filters just narrow the search space.
    """
    query_lower = query.lower()
    result = {}

    # Extract tickers — both explicit (AAPL) and by company name (Apple)
    known_tickers = _load_known_tickers()
    found_tickers = set()

    # Check for explicit tickers (uppercase, 1-5 letters)
    for word in re.findall(r"\b[A-Z]{1,5}\b", query):
        if word in known_tickers:
            found_tickers.add(word)

    # Check for company name aliases (word boundary matching to avoid
    # false positives like "NVIDIA" matching the "ge" alias)
    for alias, ticker in _COMPANY_ALIASES.items():
        pattern = r"\b" + re.escape(alias) + r"\b"
        if re.search(pattern, query_lower):
            found_tickers.add(ticker)

    if found_tickers:
        result["tickers"] = sorted(found_tickers)

    # Extract sector hints
    sector_keywords = {
        "tech": ["tech", "technology", "software", "semiconductor"],
        "finance": ["finance", "financial", "bank", "banking", "insurance"],
        "pharma": ["pharma", "pharmaceutical", "drug", "biotech", "healthcare"],
        "consumer": ["consumer", "retail", "food", "beverage"],
        "energy": ["energy", "oil", "gas", "petroleum"],
        "industrial": ["industrial", "manufacturing", "aerospace", "defense"],
        "telecom": ["telecom", "telecommunications", "communications"],
    }
    found_sectors = set()
    for sector, keywords in sector_keywords.items():
        if any(kw in query_lower for kw in keywords):
            found_sectors.add(sector)
    if found_sectors:
        result["sectors"] = sorted(found_sectors)

    # Extract section hints
    for hint_key, section_name in _SECTION_HINTS.items():
        if hint_key in query_lower:
            result["section_hint"] = section_name
            break

    # Extract filing type
    if "10-k" in query_lower or "annual" in query_lower:
        result["filing_type"] = "10-K"
    elif "10-q" in query_lower or "quarterly" in query_lower:
        result["filing_type"] = "10-Q"

    # Extract years
    years = re.findall(r"\b(20[1-2]\d)\b", query)
    if years:
        result["years"] = sorted(set(years))

    return result


def _build_where_clause(parsed: dict, access_filter: dict | None) -> dict | None:
    """
    Combine query-derived filters with access control filters into
    a single ChromaDB 'where' clause.
    """
    conditions = []

    # Access control filter (from auth.py)
    if access_filter:
        if "$and" in access_filter:
            conditions.extend(access_filter["$and"])
        else:
            conditions.append(access_filter)

    # Ticker filter
    if "tickers" in parsed:
        tickers = parsed["tickers"]
        if len(tickers) == 1:
            conditions.append({"ticker": tickers[0]})
        else:
            conditions.append({"ticker": {"$in": tickers}})

    # Sector filter (only if no specific tickers — tickers are more precise)
    if "sectors" in parsed and "tickers" not in parsed:
        sectors = parsed["sectors"]
        if len(sectors) == 1:
            conditions.append({"sector": sectors[0]})
        else:
            conditions.append({"sector": {"$in": sectors}})

    # Filing type filter
    if "filing_type" in parsed:
        conditions.append({"filing_type": parsed["filing_type"]})

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def _format_chunks(results: dict) -> list[dict]:
    """Convert raw ChromaDB results into a list of chunk dicts."""
    chunks = []
    if results["ids"] and results["ids"][0]:
        for i, (chunk_id, text, metadata, distance) in enumerate(zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )):
            chunks.append({
                "id": chunk_id,
                "text": text,
                "metadata": metadata,
                "distance": distance,
                "rank": i + 1,
            })
    return chunks


def _add_filter(where: dict | None, new_filter: dict) -> dict:
    """Append a filter condition to an existing where clause."""
    if where is None:
        return new_filter
    if "$and" in where:
        where["$and"].append(new_filter)
        return where
    return {"$and": [where, new_filter]}


def _find_matching_sections(collection, ticker: str, section_hint: str) -> list[str]:
    """
    Find actual section names in the index that match a section hint.

    Section names vary across companies (e.g., "Risk Factors" vs "Risk Factors."
    with trailing period). This looks up what actually exists for a given ticker
    and returns section names that contain the hint text (case-insensitive).
    """
    results = collection.get(where={"ticker": ticker}, limit=1000, include=["metadatas"])
    hint_lower = section_hint.lower()
    matches = set()
    for m in results["metadatas"]:
        # Match if the section name starts with the hint (handles trailing periods)
        if m["section_name"].lower().startswith(hint_lower):
            matches.add(m["section_name"])
    return sorted(matches)


def _retrieve_balanced(
    tickers: list[str],
    query_embedding: list[float],
    access_filter: dict | None,
    parsed: dict,
    top_k: int,
    collection,
) -> list[dict]:
    """
    Balanced retrieval for multi-company queries.

    Pure vector search is biased toward whichever company's language is
    closest to the query embedding. For comparative questions ("compare
    Apple, Tesla, and JPMorgan"), one company can dominate all top_k slots.

    Fix: retrieve per-ticker with equal allocation, then merge by distance.
    When a section hint exists (e.g., "Risk Factors"), filter to that section
    first, with a fallback to unfiltered retrieval if no matching sections exist.
    """
    per_ticker = max(top_k // len(tickers), 5)
    section_hint = parsed.get("section_hint")
    all_chunks = []
    seen_ids = set()

    for ticker in tickers:
        # Start with ticker filter (deep copy to avoid mutating shared state)
        base = copy.deepcopy(access_filter) if access_filter else None
        where = _add_filter(base, {"ticker": ticker})

        # Add filing type if specified
        if "filing_type" in parsed:
            where = _add_filter(where, {"filing_type": parsed["filing_type"]})

        # Add section filter if we have a hint and matching sections exist
        section_where = None
        if section_hint:
            matching = _find_matching_sections(collection, ticker, section_hint)
            if matching:
                section_base = copy.deepcopy(where)
                if len(matching) == 1:
                    section_where = _add_filter(section_base, {"section_name": matching[0]})
                else:
                    section_where = _add_filter(section_base, {"section_name": {"$in": matching}})

        # Try section-filtered query first, fall back to unfiltered
        if section_where:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=per_ticker,
                where=section_where,
            )
            # If section filter returned too few results, supplement with unfiltered
            section_chunks = _format_chunks(results)
            if len(section_chunks) < per_ticker:
                fallback = collection.query(
                    query_embeddings=[query_embedding],
                    n_results=per_ticker,
                    where=where,
                )
                for chunk in _format_chunks(fallback):
                    if chunk["id"] not in {c["id"] for c in section_chunks}:
                        section_chunks.append(chunk)
                        if len(section_chunks) >= per_ticker:
                            break
            for chunk in section_chunks:
                if chunk["id"] not in seen_ids:
                    seen_ids.add(chunk["id"])
                    all_chunks.append(chunk)
        else:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=per_ticker,
                where=where,
            )
            for chunk in _format_chunks(results):
                if chunk["id"] not in seen_ids:
                    seen_ids.add(chunk["id"])
                    all_chunks.append(chunk)

    # Sort by distance (best matches first) and re-rank
    all_chunks.sort(key=lambda c: c["distance"])
    for i, chunk in enumerate(all_chunks):
        chunk["rank"] = i + 1

    return all_chunks[:top_k]


def retrieve(
    query: str,
    user: User,
    top_k: int | None = None,
    collection=None,
) -> dict:
    """
    Full retrieval pipeline: parse → filter → embed → search → return.

    For multi-company queries, uses balanced per-ticker retrieval to ensure
    every mentioned company is represented. For single-company or broad
    queries, uses standard vector search.

    Args:
        query: Natural language question
        user: User object for access control
        top_k: Number of chunks to retrieve (default: config.TOP_K_RETRIEVAL)
        collection: ChromaDB collection (default: load from disk)

    Returns:
        {
            "query": original query text,
            "parsed": parsed query filters,
            "access_filter": access control filter applied,
            "where_clause": combined ChromaDB filter,
            "chunks": list of {id, text, metadata, distance},
        }
    """
    top_k = top_k or config.TOP_K_RETRIEVAL
    collection = collection or load_index()

    # Step 1: Parse query
    parsed = parse_query(query)

    # Step 2: Build access filter
    access_filter = get_access_filter(user)

    # Step 3: Embed query (one API call)
    query_embedding = embed_query(query)

    # Step 4: Search — balanced retrieval for multi-ticker, standard otherwise
    tickers = parsed.get("tickers", [])

    if len(tickers) > 1:
        # Multi-company query: retrieve per-ticker to guarantee representation
        chunks = _retrieve_balanced(
            tickers, query_embedding, access_filter, parsed, top_k, collection,
        )
        where_clause = _build_where_clause(parsed, access_filter)
    else:
        # Single-company or broad query: standard vector search
        where_clause = _build_where_clause(parsed, access_filter)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_clause,
        )
        chunks = _format_chunks(results)

    return {
        "query": query,
        "parsed": parsed,
        "access_filter": access_filter,
        "where_clause": where_clause,
        "chunks": chunks,
    }
