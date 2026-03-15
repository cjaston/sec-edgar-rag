# SEC Filing Research Tool

An AI-powered research assistant that answers natural language questions about public company SEC filings (10-K and 10-Q reports). Ask a question in plain English, get a sourced, cited answer grounded entirely in real financial documents — produced in a single LLM API call.

---

## What It Does

> *"What are the primary risk factors facing Apple, Tesla, and JPMorgan, and how do they compare?"*

> *"How has NVIDIA's revenue and growth outlook changed over the last two years?"*

> *"What regulatory risks do the major pharmaceutical companies face?"*

The system retrieves relevant passages from 246 SEC filings, injects them as context into one LLM call, and returns a structured answer with citations pointing to the exact filing, section, and date — so every claim is verifiable.

---

## At a Glance

| | |
|---|---|
| **Corpus** | 246 SEC filings (10-K and 10-Q) across 54 companies, 7 sectors, 2023–2025 |
| **Pipeline** | Preprocess → Deduplicate → Chunk → Embed → Index → Retrieve → Prompt → LLM → Audit |
| **Index** | 13,953 searchable chunks in ChromaDB with 18 metadata fields each |
| **Retrieval** | Filter-first metadata search + balanced per-entity semantic retrieval |
| **LLM** | Multi-provider — OpenAI, Anthropic, Google — switchable via config |
| **Accuracy** | 34 claims tested against raw filings: 97% exact match, 0 hallucinations |
| **Interface** | Web UI (Streamlit) and CLI with streaming responses |

---

## Features

### Intelligent Retrieval
- **Filter-first search** — metadata filters (company, sector, filing type) applied before semantic similarity, guaranteeing precision
- **Balanced multi-company retrieval** — queries comparing multiple companies allocate retrieval slots per entity, preventing one company from dominating results
- **Section-aware filtering** — handles metadata variations across filings (e.g., "Risk Factors" vs "Risk Factors.") via fuzzy matching

### Enterprise Security
- **Role-based access control** — five demo roles (admin, tech/finance/pharma analyst, restricted) with access enforced at the database layer. Restricted chunks never enter search results.
- **Multi-tenant isolation** — every chunk carries `tenant_id` and `access_level` metadata. In production, tenant identity comes from SSO/OAuth; the filtering mechanism stays identical.
- **Full audit trail** — every query logged to SQLite: user, query, chunks retrieved, model, tokens, latency, errors. Schema designed for direct migration to Postgres.

### Data Lineage & Citation
- Every answer cites the specific filing, section, and date
- Source integrity verified via SHA-256 hashes
- Trace any claim back to the exact paragraph in the original SEC document

### Multi-Provider LLM
- Switch between OpenAI (GPT-4o), Anthropic (Claude Sonnet 4.6), and Google (Gemini) with one config change
- Standardized response interface — the pipeline is provider-agnostic
- Streaming output in both UI and CLI

### Zero Hardcoding
- **Sectors** resolved dynamically from SEC EDGAR via SIC codes — not a lookup table
- **Section names** parsed from each filing's own Table of Contents — adapts automatically when the SEC adds new items
- **All parameters** (chunk size, retrieval depth, model, temperature) configurable via environment variables

---

## Installation

### Prerequisites

| Requirement | How to Install |
|---|---|
| **Python 3.8+** | macOS: `brew install python@3.11` · Windows: [python.org/downloads](https://www.python.org/downloads/) · Linux: `sudo apt install python3.11` |
| **Git LFS** | macOS: `brew install git-lfs` · Windows/Linux: [git-lfs.github.com](https://git-lfs.github.com/) |
| **API Key** | At least one: [OpenAI](https://platform.openai.com/api-keys), [Anthropic](https://console.anthropic.com/settings/keys), or [Google](https://aistudio.google.com/apikey) |

### Step 1: Clone the Repository

```bash
git clone https://github.com/cjaston/sec-edgar-rag.git
cd sec-edgar-rag
```

**Important:** Git LFS must be installed *before* cloning. The pre-built vector index (~530MB) is stored via Git LFS. If you cloned without it, run:

```bash
git lfs install
git lfs pull
```

### Step 2: Run Setup

```bash
./setup.sh
```

This will:
- Detect your Python installation (3.8+)
- Create a virtual environment (`venv/`)
- Install all dependencies
- Generate a `.env` config file from the template

### Step 3: Add Your API Key

Open `.env` and add at least one provider key:

```bash
# Anthropic (recommended — best answer quality for financial analysis)
ANTHROPIC_API_KEY=sk-ant-your-key-here

# OpenAI (faster responses, lower latency)
OPENAI_API_KEY=sk-your-key-here

# Google (optional)
GOOGLE_API_KEY=your-key-here
```

You can also enter API keys directly in the Web UI sidebar — no file editing required.

### Step 4: Launch

```bash
./run.sh
```

This opens the Web UI in your browser at `http://localhost:8501`.

---

## Usage

### Web UI (Default)

```bash
./run.sh
```

The Streamlit interface provides:
- **Chat interface** — ask questions, get streaming answers with citations
- **Role selector** — switch between admin, analyst, and restricted roles to see access control in action
- **Model picker** — choose provider (OpenAI/Anthropic/Google) and model
- **API key entry** — enter keys directly in the sidebar
- **Verbose mode** — toggle to see the full retrieval pipeline (query parsing, filters, chunk rankings, token counts)
- **Corpus stats** — total indexed chunks and coverage
- **Query history** — review past questions, models used, and performance metrics

### CLI

```bash
./run.sh --cli                           # Interactive mode (arrow key selection)
./run.sh --cli -v                        # Verbose: show full pipeline
./run.sh --cli --role admin              # Skip role picker
./run.sh --cli --role pharma_analyst -v  # Combine flags
```

Or directly:

```bash
source venv/bin/activate
python scripts/query.py                  # Interactive mode
python scripts/query.py -v               # Verbose pipeline
```

### Switching LLM Providers

Change the provider in `.env` or in the Web UI sidebar:

```bash
# In .env:
LLM_PROVIDER=anthropic          # or: openai, google
LLM_MODEL=claude-sonnet-4-6     # or: gpt-4o, gemini-2.0-flash
```

No code changes needed. The system automatically adapts message formatting, streaming, and token counting per provider.

---

## How It Works

```
User question (natural language)
  → Parse: extract tickers, sectors, section hints, filing type
  → Filter: metadata filters applied BEFORE semantic search
  → Embed: single API call for query vector
  → Retrieve: top-K chunks from ChromaDB within filtered set
  → Prompt: format chunks with source headers + citation rules
  → LLM: single API call produces the answer
  → Audit: log query, response, tokens, latency to SQLite
  → Return: answer + citations + pipeline details
```

### The Data Pipeline

Each SEC filing goes through five stages before it's searchable:

1. **Metadata extraction** — Company name, ticker, filing type, date, CIK parsed from structured headers
2. **XBRL stripping** — Machine-readable data removed via 3-strategy fallback (handles 100% of corpus including edge cases like Eli Lilly and Netflix)
3. **Section extraction** — Filing split into labeled sections by parsing Item headings against the filing's own Table of Contents — not hardcoded
4. **Deduplication** — Fragmented sections merged by (Item, Part) key. 100% content retention verified programmatically by comparing total character counts before and after
5. **Chunking & embedding** — ~1,500-token chunks with 200-token overlap. Content-hash dedup cache avoids re-embedding identical boilerplate across filings

**Result:** 246 filings → 3,001 sections → 13,953 chunks, each with 18 metadata fields.

---

## Project Structure

```
sec-edgar-rag/
├── config.py                       # All parameters configurable via env vars
├── pyproject.toml                  # Package metadata and dependencies
├── requirements.txt                # Pip dependency list
├── setup.sh                        # Automated setup
├── run.sh                          # Launcher (UI or CLI)
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
│   │   ├── llm.py                  # Multi-provider LLM with streaming
│   │   └── rag.py                  # End-to-end RAG orchestrator
│   │
│   ├── enterprise/                 # Access control & compliance
│   │   ├── auth.py                 # Role-based access with ChromaDB filters
│   │   └── audit.py                # SQLite query audit logging
│   │
│   ├── ui/                         # Streamlit web interface
│   │   ├── app.py                  # Chat UI with streaming, role picker, pipeline view
│   │   └── assets/                 # Logo and static assets
│   │
│   └── utils/
│       └── sector_lookup.py        # Dynamic SIC → sector via SEC EDGAR API
│
├── scripts/
│   ├── build_index.py              # Full pipeline: preprocess → chunk → embed → index
│   └── query.py                    # Interactive CLI
│
├── docs/                           # Test results and presentation
│   ├── prompt_tests/               # Claude vs GPT-4o model comparison
│   └── final_pres_eliza.pptx       # Panel presentation deck
├── edgar_corpus/                   # 246 raw SEC filing text files
└── chroma_db/                      # Pre-built vector index (Git LFS, ~530MB)
```

---

## Configuration

All parameters live in `config.py` with environment variable overrides. Key settings:

| Parameter | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `openai` | LLM provider: `openai`, `anthropic`, or `google` |
| `LLM_MODEL` | `gpt-4o` | Model name (auto-set per provider in UI) |
| `FINAL_CHUNKS` | `18` | Number of chunks included in LLM prompt |
| `TOP_K_RETRIEVAL` | `30` | Chunks retrieved before final selection |
| `CHUNK_SIZE` | `1500` | Tokens per chunk |
| `CHUNK_OVERLAP` | `200` | Token overlap between chunks |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model |
| `LLM_TEMPERATURE` | `0.1` | Response temperature |

Override any parameter in `.env` without touching code.

---

## Rebuilding the Index

A pre-built index ships via Git LFS — no rebuild required for querying. To rebuild from the raw filings (requires an OpenAI API key for embeddings):

```bash
source venv/bin/activate
python scripts/build_index.py
```

Runs the full pipeline in ~5 minutes. Costs ~$0.34 in embedding API calls. The index persists to `./chroma_db/`.

---

## Tested Results

All three example queries from the assessment were tested on both Claude Sonnet 4.6 and GPT-4o. Every factual claim was verified against the raw filing text.

| Query | Claude (tokens/latency) | GPT-4o (tokens/latency) |
|---|---|---|
| Risk factors: Apple, Tesla, JPMorgan | 1,687 tokens / 37s | 783 tokens / 9s |
| NVIDIA revenue & growth | 1,175 tokens / 25s | 677 tokens / 9s |
| Pharma regulatory risks | 1,621 tokens / 39s | 819 tokens / 8s |

**Grounding accuracy:** 33/34 claims confirmed as exact quotes from the corpus. 1 minor paraphrase. 0 hallucinations.

Full test results with pipeline details and verification notes are in `docs/prompt_tests/`.
