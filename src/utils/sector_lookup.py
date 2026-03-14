"""
Resolves company sectors from SEC EDGAR using SIC codes.

Uses the edgartools library (1.8k GitHub stars, actively maintained) to pull
each company's SIC code directly from SEC EDGAR. We then map the SIC major
group (2-digit prefix) to a simplified sector label using the official
SEC/OSHA Standard Industrial Classification division structure.

Results are cached locally so the SEC API is only hit once per company.
If the corpus changes (new companies added), sectors resolve automatically.
"""

import json
import time

import config

_identity_set = False


def _ensure_identity():
    """Set the SEC EDGAR identity on first use, not on import."""
    global _identity_set
    if not _identity_set:
        from edgar import set_identity
        set_identity("EdgarRAG sec-filing-research-tool")
        _identity_set = True


def sic_to_sector(sic_code: str | int) -> str:
    """Map a SIC code to a sector using its 2-digit major group prefix."""
    major_group = str(sic_code).zfill(4)[:2]
    return config.SIC_MAJOR_GROUP_TO_SECTOR.get(major_group, "other")


def _load_cache() -> dict:
    if config.SIC_CACHE_PATH.exists():
        with open(config.SIC_CACHE_PATH) as f:
            return json.load(f)
    return {}


def _save_cache(cache: dict) -> None:
    with open(config.SIC_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2, sort_keys=True)


def lookup_company(ticker: str) -> dict | None:
    """
    Look up a company's SIC code, industry, and sector from SEC EDGAR.

    Returns:
        {"sic": "3571", "industry": "Electronic Computers", "sector": "tech"}
        or None if lookup fails.
    """
    _ensure_identity()
    try:
        from edgar import Company
        company = Company(ticker)
        sic = company.sic
        industry = company.industry
        sector = sic_to_sector(sic)
        return {"sic": sic, "industry": industry, "sector": sector}
    except Exception:
        return None


def resolve_sectors(tickers: list[str]) -> dict[str, str]:
    """
    Resolve sectors for all tickers. Uses cache, only hits SEC for new companies.

    Args:
        tickers: List of stock tickers (e.g., ["AAPL", "JPM", "PFE"])

    Returns:
        {"AAPL": "tech", "JPM": "finance", ...}
    """
    cache = _load_cache()
    sector_map = {}

    for ticker in sorted(set(t.upper() for t in tickers)):
        if ticker in cache:
            sector_map[ticker] = cache[ticker]["sector"]
            continue

        result = lookup_company(ticker)
        if result:
            cache[ticker] = result
            sector_map[ticker] = result["sector"]
            print(f"  {ticker}: SIC {result['sic']} ({result['industry']}) -> {result['sector']}")
        else:
            cache[ticker] = {"sic": "0000", "industry": "Unknown", "sector": "other"}
            sector_map[ticker] = "other"
            print(f"  {ticker}: lookup failed -> other")

        # SEC rate limit: 10 req/sec
        time.sleep(0.15)

    _save_cache(cache)
    return sector_map


def get_sector(ticker: str) -> str:
    """Get sector for a single ticker from cache. Returns 'other' if not cached."""
    cache = _load_cache()
    entry = cache.get(ticker.upper())
    return entry["sector"] if entry else "other"
