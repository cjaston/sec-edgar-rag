"""
End-to-end RAG orchestrator.

Ties together retrieval, prompt construction, LLM call, and audit logging.
This is the single entry point for answering a question — one function call
that runs the entire pipeline and returns a structured result with full
transparency into every step.
"""

import time

import config
from src.query.retriever import retrieve
from src.query.prompt import build_prompt
from src.query.llm import call_llm
from src.enterprise.auth import User
from src.enterprise.audit import log_query
from src.pipeline.chunker import count_tokens


def ask(
    query: str,
    user: User,
    provider: str | None = None,
    model: str | None = None,
    top_k: int | None = None,
    final_chunks: int | None = None,
    collection=None,
    verbose: bool = False,
    stream: bool = False,
) -> dict:
    """
    Answer a question using the full RAG pipeline.

    Pipeline:
      1. Retrieve relevant chunks (filtered by access control + query parsing)
      2. Select top chunks for the prompt
      3. Build prompt with context
      4. Single LLM API call
      5. Log to audit database

    Args:
        query: Natural language question
        user: User object for access control
        provider: LLM provider override
        model: LLM model override
        top_k: Number of chunks to retrieve
        final_chunks: Number of chunks to include in prompt
        collection: ChromaDB collection override
        verbose: If True, print pipeline steps to stdout

    Returns:
        {
            "answer": str,
            "citations": list of source metadata,
            "pipeline": {step-by-step details},
            "usage": {token counts, latency},
        }
    """
    start_time = time.time()
    final_chunks = final_chunks or config.FINAL_CHUNKS

    # ── Step 1: Retrieve ──
    if verbose:
        print(f"\n{'─' * 60}")
        print(f"Query: {query}")
        print(f"User: {user.name} ({user.role})")
        print(f"{'─' * 60}")

    retrieval = retrieve(query, user, top_k=top_k, collection=collection)

    if verbose:
        parsed = retrieval["parsed"]
        print(f"\n[1] Query Parsing:")
        if parsed.get("tickers"):
            print(f"    Tickers: {', '.join(parsed['tickers'])}")
        if parsed.get("sectors"):
            print(f"    Sectors: {', '.join(parsed['sectors'])}")
        if parsed.get("section_hint"):
            print(f"    Section: {parsed['section_hint']}")
        if parsed.get("filing_type"):
            print(f"    Type: {parsed['filing_type']}")
        if not parsed:
            print(f"    (no specific filters extracted — searching broadly)")

        print(f"\n[2] Retrieval:")
        print(f"    Access filter: {retrieval['access_filter'] or 'none (admin)'}")
        print(f"    Where clause: {retrieval['where_clause'] or 'none'}")
        print(f"    Chunks found: {len(retrieval['chunks'])}")

    # ── Step 2: Select top chunks for prompt ──
    # For multi-company queries, balance the final selection so every
    # company gets fair representation in the LLM context.
    tickers = retrieval["parsed"].get("tickers", [])
    all_chunks = retrieval["chunks"]

    if len(tickers) > 1 and all_chunks:
        per_company = max(final_chunks // len(tickers), 2)
        selected = []
        by_ticker = {t: [] for t in tickers}
        overflow = []
        for c in all_chunks:
            t = c["metadata"]["ticker"]
            if t in by_ticker and len(by_ticker[t]) < per_company:
                by_ticker[t].append(c)
            else:
                overflow.append(c)
        for t in tickers:
            selected.extend(by_ticker[t])
        # Fill remaining slots from overflow (best distance first)
        remaining = final_chunks - len(selected)
        if remaining > 0:
            selected.extend(overflow[:remaining])
    else:
        selected = all_chunks[:final_chunks]

    if not selected:
        elapsed = int((time.time() - start_time) * 1000)
        error_msg = "No relevant chunks found. "
        if retrieval["access_filter"]:
            error_msg += f"Your access level ({user.role}) may not include the requested data."
        else:
            error_msg += "Try rephrasing your question."

        log_query(
            user_id=user.name,
            user_role=user.role,
            query_text=query,
            chunks_used=0,
            latency_ms=elapsed,
            error=error_msg,
        )

        return {
            "answer": error_msg,
            "citations": [],
            "pipeline": {"retrieval": retrieval, "selected_chunks": 0},
            "usage": {"input_tokens": 0, "output_tokens": 0, "latency_ms": elapsed},
        }

    if verbose:
        print(f"    Selected for prompt: {len(selected)} (of {len(retrieval['chunks'])})")
        for c in selected[:5]:
            m = c["metadata"]
            print(f"      #{c['rank']} {m['ticker']} | {m['section_name']} | {m['filing_date']} | dist={c['distance']:.4f}")
        if len(selected) > 5:
            print(f"      ... and {len(selected) - 5} more")

    # ── Step 3: Build prompt ──
    messages = build_prompt(query, selected)
    prompt_tokens = count_tokens(messages[0]["content"] + messages[1]["content"])

    if verbose:
        print(f"\n[3] Prompt:")
        print(f"    Context chunks: {len(selected)}")
        print(f"    Prompt tokens: ~{prompt_tokens}")

    # ── Step 4: LLM call ──
    provider = provider or config.LLM_PROVIDER
    model = model or config.LLM_MODEL

    if verbose:
        print(f"\n[4] LLM Call:")
        print(f"    Provider: {provider}")
        print(f"    Model: {model}")
        print(f"    Temperature: {config.LLM_TEMPERATURE}")

    if stream:
        print()  # blank line before streamed output

    llm_response = call_llm(
        messages=messages,
        provider=provider,
        model=model,
        stream=stream,
    )

    elapsed = int((time.time() - start_time) * 1000)

    if verbose:
        print(f"    Input tokens: {llm_response['input_tokens']}")
        print(f"    Output tokens: {llm_response['output_tokens']}")
        print(f"    Latency: {elapsed}ms")

    # ── Step 5: Build citations ──
    citations = []
    seen = set()
    for c in selected:
        m = c["metadata"]
        key = (m["ticker"], m["filing_type"], m["filing_date"], m["section_name"])
        if key not in seen:
            seen.add(key)
            citations.append({
                "ticker": m["ticker"],
                "company": m["company_name"],
                "filing_type": m["filing_type"],
                "filing_date": m["filing_date"],
                "section": m["section_name"],
                "source_url": m["source_url"],
            })

    # ── Step 6: Audit log ──
    log_query(
        user_id=user.name,
        user_role=user.role,
        query_text=query,
        chunks_retrieved=[c["id"] for c in selected],
        chunks_used=len(selected),
        llm_provider=llm_response["provider"],
        llm_model=llm_response["model"],
        response_text=llm_response["content"],
        input_tokens=llm_response["input_tokens"],
        output_tokens=llm_response["output_tokens"],
        latency_ms=elapsed,
    )

    return {
        "answer": llm_response["content"],
        "citations": citations,
        "pipeline": {
            "parsed": retrieval["parsed"],
            "access_filter": retrieval["access_filter"],
            "where_clause": retrieval["where_clause"],
            "chunks_retrieved": len(retrieval["chunks"]),
            "chunks_used": len(selected),
        },
        "usage": {
            "provider": llm_response["provider"],
            "model": llm_response["model"],
            "input_tokens": llm_response["input_tokens"],
            "output_tokens": llm_response["output_tokens"],
            "latency_ms": elapsed,
        },
    }
