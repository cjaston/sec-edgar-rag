"""
Centralized configuration for the SEC Filing Research Tool.

All parameters have sensible defaults and can be overridden via environment
variables or .env file. This means behavior can be tuned for different corpora,
use cases, or client requirements without touching code.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
PROJECT_ROOT = Path(__file__).parent
load_dotenv(PROJECT_ROOT / ".env")


def _env(key: str, default: str) -> str:
    return os.getenv(key, default)


def _env_int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


def _env_float(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))


# ── API Keys ──────────────────────────────────────────────────────────────────
# At least one provider key is required. Keys can also be entered in the UI.

OPENAI_API_KEY = _env("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY", "")
GOOGLE_API_KEY = _env("GOOGLE_API_KEY", "")


# ── Corpus & Paths ───────────────────────────────────────────────────────────

CORPUS_DIR = Path(_env("CORPUS_DIR", str(PROJECT_ROOT / "edgar_corpus")))
CHROMA_DIR = Path(_env("CHROMA_DIR", str(PROJECT_ROOT / "chroma_db")))
AUDIT_DB_PATH = Path(_env("AUDIT_DB_PATH", str(PROJECT_ROOT / "audit.db")))
CHROMA_COLLECTION = _env("CHROMA_COLLECTION", "sec_filings")


# ── Chunking ──────────────────────────────────────────────────────────────────
# Section-aware chunking. Chunk size in tokens, not characters.
# 1500 tokens validated as optimal for this corpus: large enough to preserve
# context within a section, small enough for precise retrieval.

CHUNK_SIZE = _env_int("CHUNK_SIZE", 1500)
CHUNK_OVERLAP = _env_int("CHUNK_OVERLAP", 200)
MIN_CHUNK_SIZE = _env_int("MIN_CHUNK_SIZE", 200)      # Characters — for section filtering
MIN_CHUNK_TOKENS = _env_int("MIN_CHUNK_TOKENS", 30)   # Tokens — for chunk filtering


# ── Embedding ─────────────────────────────────────────────────────────────────
# text-embedding-3-small: best cost/performance ratio at our scale (~15K chunks).
# text-embedding-3-large available via env override if higher recall is needed.

EMBEDDING_MODEL = _env("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = _env_int("EMBEDDING_DIMENSIONS", 1536)
EMBEDDING_BATCH_SIZE = _env_int("EMBEDDING_BATCH_SIZE", 100)


# ── LLM ───────────────────────────────────────────────────────────────────────
# Multi-provider support. Default OpenAI GPT-4o. Switch via env or UI.

LLM_PROVIDER = _env("LLM_PROVIDER", "openai")
LLM_MODEL = _env("LLM_MODEL", "gpt-4o")
LLM_TEMPERATURE = _env_float("LLM_TEMPERATURE", 0.1)
LLM_MAX_TOKENS = _env_int("LLM_MAX_TOKENS", 4096)

# Provider-specific model defaults (used when switching providers in UI)
PROVIDER_MODELS = {
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-6",
    "google": "gemini-2.0-flash",
}


# ── Retrieval ─────────────────────────────────────────────────────────────────
# Two-stage retrieval: broad semantic search (TOP_K), then rerank to FINAL_CHUNKS.
# Higher TOP_K casts a wider net; FINAL_CHUNKS controls prompt context size.

TOP_K_RETRIEVAL = _env_int("TOP_K_RETRIEVAL", 30)
FINAL_CHUNKS = _env_int("FINAL_CHUNKS", 18)
SIMILARITY_THRESHOLD = _env_float("SIMILARITY_THRESHOLD", 0.3)


# ── Access Control ────────────────────────────────────────────────────────────
# Enterprise multi-tenant pattern. Default is open access for demo.

DEFAULT_ACCESS_LEVEL = _env("DEFAULT_ACCESS_LEVEL", "public")
DEFAULT_TENANT_ID = _env("DEFAULT_TENANT_ID", "demo")


# ── Sector Classification ─────────────────────────────────────────────────────
# Sectors are resolved automatically at index time using the edgartools library,
# which pulls each company's SIC code from SEC EDGAR.
#
# We map SIC major groups (2-digit prefixes from the official SEC/OSHA standard)
# to simplified sector labels. The SEC organizes SIC into 10 Divisions (A-J);
# we subdivide Division D (Manufacturing) and I (Services) where the 2-digit
# major group provides a clear industry signal.
#
# Reference: https://www.osha.gov/data/sic-manual

SIC_MAJOR_GROUP_TO_SECTOR = {
    # Division A: Agriculture, Forestry, Fishing (01-09)
    "01": "agriculture", "02": "agriculture", "07": "agriculture",
    "08": "agriculture", "09": "agriculture",
    # Division B: Mining (10-14)
    "10": "mining", "12": "mining", "13": "energy", "14": "mining",
    # Division C: Construction (15-17)
    "15": "construction", "16": "construction", "17": "construction",
    # Division D: Manufacturing (20-39)
    "20": "consumer",    # Food
    "21": "consumer",    # Tobacco
    "22": "consumer",    # Textiles
    "23": "consumer",    # Apparel
    "24": "industrial",  # Lumber & Wood
    "25": "consumer",    # Furniture
    "26": "industrial",  # Paper
    "27": "consumer",    # Printing & Publishing
    "28": "pharma",      # Chemicals & Pharma (SIC 2800-2899)
    "29": "energy",      # Petroleum Refining
    "30": "consumer",    # Rubber & Plastics
    "31": "consumer",    # Leather
    "32": "industrial",  # Stone, Clay, Glass
    "33": "industrial",  # Primary Metals
    "34": "industrial",  # Fabricated Metals
    "35": "tech",        # Computer & Office Equipment, Industrial Machinery
    "36": "tech",        # Electronic & Electrical Equipment
    "37": "industrial",  # Transportation Equipment (aircraft, vehicles, ships)
    "38": "tech",        # Instruments & Related
    "39": "consumer",    # Misc Manufacturing
    # Division E: Transportation, Communications, Utilities (40-49)
    "40": "industrial",  # Railroads
    "41": "industrial",  # Transit
    "42": "industrial",  # Trucking & Warehousing
    "43": "industrial",  # USPS
    "44": "industrial",  # Water Transportation
    "45": "industrial",  # Air Transportation
    "46": "industrial",  # Pipelines
    "47": "industrial",  # Transportation Services
    "48": "telecom",     # Communications
    "49": "energy",      # Electric, Gas, Sanitary Services
    # Division F: Wholesale Trade (50-51)
    "50": "consumer",    # Durable Goods
    "51": "consumer",    # Nondurable Goods
    # Division G: Retail Trade (52-59)
    "52": "consumer", "53": "consumer", "54": "consumer", "55": "consumer",
    "56": "consumer", "57": "consumer", "58": "consumer", "59": "consumer",
    # Division H: Finance, Insurance, Real Estate (60-67)
    "60": "finance", "61": "finance", "62": "finance", "63": "finance",
    "64": "finance", "65": "finance", "67": "finance",
    # Division I: Services (70-89)
    "70": "consumer",    # Hotels & Lodging
    "72": "consumer",    # Personal Services
    "73": "tech",        # Business Services (incl. software, data processing)
    "75": "consumer",    # Auto Repair & Services
    "76": "consumer",    # Misc Repair
    "78": "consumer",    # Motion Pictures
    "79": "consumer",    # Amusement & Recreation
    "80": "healthcare",  # Health Services
    "81": "consumer",    # Legal Services
    "82": "consumer",    # Educational Services
    "83": "consumer",    # Social Services
    "84": "consumer",    # Museums
    "86": "consumer",    # Membership Organizations
    "87": "tech",        # Engineering & Management Services
    "89": "consumer",    # Misc Services
    # Division J: Public Administration (91-99)
    "91": "government", "92": "government", "93": "government",
    "94": "government", "95": "government", "96": "government",
    "97": "government", "99": "government",
}

# Cache file for resolved SIC lookups — avoids re-hitting the SEC API
SIC_CACHE_PATH = Path(_env("SIC_CACHE_PATH", str(PROJECT_ROOT / "sic_cache.json")))
