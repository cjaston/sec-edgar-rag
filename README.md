# SEC Filing Research Tool

An AI-powered research assistant that answers natural language questions about public company SEC filings. Ask a question, get a sourced, cited answer grounded entirely in real financial documents — produced in a single LLM API call.

---

## What It Does

Ask questions like:

> *"What are the primary risk factors facing Apple, Tesla, and JPMorgan, and how do they compare?"*

> *"How has NVIDIA's revenue and growth outlook changed over the last two years?"*

> *"What regulatory risks do the major pharmaceutical companies face?"*

The system retrieves relevant passages from SEC filings, injects them as context into one LLM call, and returns a structured answer with citations pointing to the exact filing, section, and date — so every claim is verifiable.

---

## At a Glance

| | |
|---|---|
| **Corpus** | 246 SEC filings (10-K and 10-Q) across 54 companies, 7 sectors, 2023–2025 |
| **Pipeline** | Preprocess → Deduplicate → Chunk → Embed → Index → Retrieve → Prompt → LLM → Audit |
| **Index** | 13,953 searchable chunks in ChromaDB with 12 metadata fields each |
| **Retrieval** | Filter-first metadata search + balanced per-entity semantic retrieval |
| **LLM** | Multi-provider — OpenAI, Anthropic, Google — switchable via config |
| **Accuracy** | 34 claims tested against raw filings: 97% exact match, 0 hallucinations |
| **Embedding Cost** | $0.34 for the entire corpus (text-embedding-3-small) |

---

## Key Capabilities

### Multi-Company Comparative Analysis

Queries mentioning multiple companies use balanced per-ticker retrieval, ensuring every company gets fair representation in the LLM context. Without this, vector search biases toward whichever company's language is closest to the query.

### Role-Based Access Control

Every chunk carries `tenant_id` and `access_level` metadata. A pharma analyst querying "risk factors" only sees pharma companies — tech and finance chunks are excluded **at the database layer**, before similarity search even runs. This is more secure than post-retrieval filtering because restricted data never leaves the store.

| Role | Access |
|------|--------|
| `admin` | All companies, all sectors, all filings |
| `tech_analyst` | Tech sector only |
| `finance_analyst` | Finance sector only |
| `pharma_analyst` | Pharma sector only |
| `restricted` | Public filings only |

### Multi-Tenant Architecture

The system supports tenant isolation out of the box. Each chunk's metadata includes a `tenant_id` field, and access filters are applied at the query layer before any search is performed. In production, tenant identity would come from SSO/OAuth — the filtering mechanism stays identical.

### Full Audit Trail

Every query is logged to SQLite: user identity, query text, chunks retrieved, LLM provider and model, response text, token usage (input + output), latency, and errors. Designed for compliance reporting, cost tracking, and quality monitoring. The schema migrates directly to Postgres for production.

### Multi-Provider LLM

Not locked into a single AI vendor. Switch between OpenAI (GPT-4o), Anthropic (Claude Sonnet), and Google (Gemini) with one config change. Each provider uses a standardized response interface — the rest of the pipeline is provider-agnostic.

### Data Lineage & Citation

Every answer cites the specific filing, section, and date. Source integrity is verified via SHA-256 hashes. You can trace any claim back to the exact paragraph in the original SEC document.

### Zero Hardcoding

- **Sectors** resolved dynamically from SEC EDGAR via SIC codes — not a hardcoded lookup table
- **Section names** parsed from each filing's own Table of Contents — adapts automatically when the SEC adds new items
- **All parameters** (chunk size, retrieval depth, model, temperature) configurable via environment variables

---

## How It Works

```
User question (natural language)
  → Parse: extract tickers, sectors, section hints, filing type
  → Filter: metadata filters applied BEFORE semantic search
  → Embed: single API call for query vector
  → Retrieve: top-K chunks from ChromaDB within filtered set
  → Prompt: format chunks with source headers + citation rules
  → LLM: single API call (the one call the system is built around)
  → Audit: log query, response, tokens, latency to SQLite
  → Return: answer + citations + pipeline details
```

### The Data Pipeline

Each SEC filing goes through five stages before it's searchable:

1. **Metadata extraction** — Company name, ticker, filing type, date, CIK parsed from structured headers
2. **XBRL stripping** — Machine-readable data removed via 3-strategy fallback (handles 100% of corpus edge cases)
3. **Section extraction** — Filing split into labeled sections by parsing Item headings against the filing's own TOC
4. **Deduplication** — Fragmented sections merged by (Item, Part) key. 100% content retention verified programmatically
5. **Chunking & embedding** — ~1,500-token chunks with 200-token overlap. Content-hash dedup cache avoids re-embedding identical text across filings

**Result:** 246 filings → 3,001 sections → 13,953 chunks, each with 12 metadata fields.

---

## Getting Started

### Prerequisites

- **Python 3.8+** — [Download here](https://www.python.org/downloads/) if not installed
- **Git LFS** — Required to clone the pre-built vector index (`brew install git-lfs` / [install guide](https://git-lfs.github.com/))
- **API Key** — At least one: OpenAI, Anthropic, or Google

### Installation

```bash
git clone https://github.com/cjaston/eliza-edgar-rag.git
cd eliza-edgar-rag
./setup.sh                        # Creates venv, installs dependencies, generates .env
```

Add your API key to `.env`:
```bash
# Edit .env — add at least one provider key
ANTHROPIC_API_KEY=sk-ant-your-key-here
# or
OPENAI_API_KEY=sk-your-key-here
```

### Running

```bash
source venv/bin/activate
python scripts/query.py
```

Use arrow keys to select your role and output mode, then ask a question.

### CLI Options

```bash
python scripts/query.py                          # Interactive setup (arrow keys)
python scripts/query.py -v                       # Verbose: full pipeline details
python scripts/query.py --role admin             # Skip role picker
python scripts/query.py --role pharma_analyst -v # Combine flags
```

---

## For Developers

### Project Structure

```
eliza-edgar-rag/
├── config.py                       # All parameters configurable via env vars
├── pyproject.toml                  # Package metadata and dependencies
├── requirements.txt                # Pip dependency list
├── setup.sh                        # Automated setup
├── run.sh                          # One-command launcher
├── .env.example                    # Environment variable template
│
├── src/
│   ├── pipeline/                   # Data ingestion & indexing
│   │   ├── preprocess.py           # Filing parser: headers, XBRL, sections
│   │   ├── chunker.py              # Token-based chunking with section dedup
│   │   ├── embeddings.py           # OpenAI embedding with content-hash cache
│   │   └── index.py                # ChromaDB index build and load
│   │
│   ├── query/                      # Query processing & generation
│   │   ├── retriever.py            # Query parsing + balanced metadata-filtered search
│   │   ├── prompt.py               # Prompt template with citation and grounding rules
│   │   ├── llm.py                  # Multi-provider LLM (OpenAI/Anthropic/Google)
│   │   └── rag.py                  # End-to-end orchestrator
│   │
│   ├── enterprise/                 # Access control & compliance
│   │   ├── auth.py                 # Role-based access with ChromaDB filters
│   │   └── audit.py                # SQLite query logging
│   │
│   └── utils/
│       └── sector_lookup.py        # Dynamic SIC → sector via SEC EDGAR API
│
├── scripts/
│   ├── build_index.py              # Full pipeline: preprocess → chunk → embed → index
│   └── query.py                    # Interactive CLI
│
├── edgar_corpus/                   # 246 raw SEC filing text files
└── chroma_db/                      # Pre-built vector index (Git LFS, ~530MB)
```

### Configuration

All parameters live in `config.py` with env var overrides. See `.env.example` for the full list. Defaults are tuned for this corpus — override without touching code.

### Rebuilding the Index

A pre-built index ships via [Git LFS](https://git-lfs.github.com/) — no API key needed to start querying. To rebuild from raw filings:

```bash
source venv/bin/activate
python scripts/build_index.py
```

Runs the full pipeline in ~5 minutes. Costs ~$0.34 in OpenAI embedding API calls.

### Sector Classification

Company sectors are resolved automatically at index time — not hardcoded. The system reads each company's CIK, looks up the SIC code from SEC EDGAR via [edgartools](https://github.com/dgunning/edgartools), and maps the 2-digit major group to a sector using the official SEC/OSHA division structure. Results are cached in `sic_cache.json`. If the corpus changes, sectors classify automatically with zero code changes.
