"""
Streamlit UI for the SEC Filing Research Tool.

Mirrors the CLI functionality with a chat interface:
- Role selection, model/provider configuration, API key entry
- Streaming responses with citations
- Pipeline details in verbose mode
- Query history from audit log
"""

import sys
import time
from pathlib import Path

# Add project root to path so imports work when launched via streamlit
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st

import config
from src.query.retriever import retrieve, parse_query
from src.query.prompt import build_prompt
from src.query.llm import call_llm
from src.enterprise.auth import get_user, describe_access, DEMO_USERS, User
from src.enterprise.audit import log_query, get_history, get_stats
from src.pipeline.chunker import count_tokens
from src.pipeline.index import load_index


# ── Page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="SEC Filing Research Tool",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Session state defaults ───────────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []
if "collection" not in st.session_state:
    st.session_state.collection = None


# ── Load index once ──────────────────────────────────────────────────────────

@st.cache_resource
def get_collection():
    return load_index()


# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.image(str(Path(__file__).parent / "assets" / "eliza_logo.png"), width=120)
    st.title("Settings")

    # Role selector
    st.subheader("User Role")
    role_options = list(DEMO_USERS.keys())
    role_descriptions = {uid: describe_access(u) for uid, u in DEMO_USERS.items()}
    selected_role = st.selectbox(
        "Role",
        role_options,
        format_func=lambda x: f"{x} — {role_descriptions[x]}",
        label_visibility="collapsed",
    )
    user = get_user(selected_role)

    st.divider()

    # Provider & Model
    st.subheader("LLM Configuration")
    provider = st.selectbox("Provider", ["anthropic", "openai", "google"])
    model_defaults = {
        "anthropic": "claude-sonnet-4-6",
        "openai": "gpt-4o",
        "google": "gemini-2.0-flash",
    }
    model = st.text_input("Model", value=model_defaults.get(provider, ""))

    # API key override
    api_key_input = st.text_input(
        f"{provider.title()} API Key (optional override)",
        type="password",
        placeholder="Uses .env key if blank",
    )
    api_key = api_key_input if api_key_input else None

    st.divider()

    # Verbose toggle
    verbose = st.toggle("Verbose mode (show pipeline)", value=False)

    st.divider()

    # Corpus stats
    st.subheader("Corpus")
    collection = get_collection()
    count = collection.count()
    st.metric("Indexed Chunks", f"{count:,}")
    st.caption("246 filings · 54 companies · 7 sectors")

    st.divider()

    # Query history
    st.subheader("Query History")
    stats = get_stats()
    if stats.get("total_queries", 0) > 0:
        col1, col2 = st.columns(2)
        col1.metric("Queries", stats["total_queries"])
        col2.metric("Avg Latency", f"{stats['avg_latency_ms']:,}ms")

        with st.expander("Recent queries", expanded=False):
            history = get_history(10)
            for h in history:
                ts = h["timestamp"][:19].replace("T", " ")
                q = h["query_text"][:80]
                st.caption(f"**{ts}** · {h['user_role']} · {h.get('llm_provider', '?')}/{h.get('llm_model', '?')}")
                st.text(q)
    else:
        st.caption("No queries yet.")

    st.divider()
    st.caption("Built for the Eliza FDE assessment")


# ── Main area ────────────────────────────────────────────────────────────────

st.title("SEC Filing Research Tool")
st.caption(f"Logged in as **{user.name}** · {describe_access(user)}")

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            st.markdown(msg["content"])
            # Show citations if stored
            if msg.get("citations"):
                with st.expander("Sources", expanded=False):
                    for c in msg["citations"]:
                        st.caption(f"• {c['company']} ({c['ticker']}) — {c['filing_type']} {c['filing_date']}, {c['section']}")
            # Show pipeline if stored
            if msg.get("pipeline") and msg.get("usage"):
                p = msg["pipeline"]
                u = msg["usage"]
                st.caption(
                    f"{u.get('provider', '?')}/{u.get('model', '?')} · "
                    f"{p.get('chunks_retrieved', '?')}→{p.get('chunks_used', '?')} chunks · "
                    f"{u.get('input_tokens', 0):,}+{u.get('output_tokens', 0):,} tokens · "
                    f"{u.get('latency_ms', 0)/1000:.1f}s"
                )
        else:
            st.markdown(msg["content"])


# ── Chat input ───────────────────────────────────────────────────────────────

if prompt := st.chat_input("Ask a question about SEC filings..."):
    # Add user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Process query
    with st.chat_message("assistant"):
        start_time = time.time()
        collection = get_collection()

        # ── Step 1: Retrieve ──
        if verbose:
            pipeline_container = st.expander("Pipeline Details", expanded=True)
            with pipeline_container:
                st.markdown("**[1] Query Parsing**")
                parsed = parse_query(prompt)
                if parsed.get("tickers"):
                    st.code(f"Tickers: {', '.join(parsed['tickers'])}")
                if parsed.get("sectors"):
                    st.code(f"Sectors: {', '.join(parsed['sectors'])}")
                if parsed.get("section_hint"):
                    st.code(f"Section: {parsed['section_hint']}")
                if not parsed:
                    st.code("(no specific filters — searching broadly)")

        retrieval = retrieve(prompt, user, collection=collection)

        if verbose:
            with pipeline_container:
                st.markdown("**[2] Retrieval**")
                st.code(f"Access filter: {retrieval['access_filter'] or 'none (admin)'}\n"
                        f"Chunks found: {len(retrieval['chunks'])}")

        # ── Step 2: Select chunks ──
        final_n = config.FINAL_CHUNKS
        tickers = retrieval["parsed"].get("tickers", [])
        all_chunks = retrieval["chunks"]

        if len(tickers) > 1 and all_chunks:
            per_company = max(final_n // len(tickers), 2)
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
            remaining = final_n - len(selected)
            if remaining > 0:
                selected.extend(overflow[:remaining])
        else:
            selected = all_chunks[:final_n]

        if not selected:
            elapsed = int((time.time() - start_time) * 1000)
            error_msg = "No relevant chunks found. "
            if retrieval["access_filter"]:
                error_msg += f"Your access level ({user.role}) may not include the requested data."
            else:
                error_msg += "Try rephrasing your question."
            st.warning(error_msg)
            log_query(
                user_id=user.name, user_role=user.role, query_text=prompt,
                chunks_used=0, latency_ms=elapsed, error=error_msg,
            )
            st.session_state.messages.append({"role": "assistant", "content": error_msg})
            st.stop()

        if verbose:
            with pipeline_container:
                st.markdown(f"**Selected:** {len(selected)} of {len(all_chunks)} chunks")
                chunk_lines = []
                for c in selected[:8]:
                    m = c["metadata"]
                    chunk_lines.append(f"{m['ticker']:5s} | {m['section_name'][:40]:40s} | {m['filing_date']} | dist={c['distance']:.4f}")
                if len(selected) > 8:
                    chunk_lines.append(f"... and {len(selected) - 8} more")
                st.code("\n".join(chunk_lines))

        # ── Step 3: Build prompt ──
        messages = build_prompt(prompt, selected)
        prompt_tokens = count_tokens(messages[0]["content"] + messages[1]["content"])

        if verbose:
            with pipeline_container:
                st.markdown("**[3] Prompt**")
                st.code(f"Context chunks: {len(selected)}\nPrompt tokens: ~{prompt_tokens:,}")

        # ── Step 4: LLM call with streaming ──
        active_provider = provider
        active_model = model

        if verbose:
            with pipeline_container:
                st.markdown("**[4] LLM Call**")
                st.code(f"Provider: {active_provider}\nModel: {active_model}\nTemperature: {config.LLM_TEMPERATURE}")

        # Stream the response
        answer_placeholder = st.empty()
        full_response = ""
        input_tokens = 0
        output_tokens = 0

        try:
            if active_provider == "anthropic":
                import anthropic
                client = anthropic.Anthropic(api_key=api_key or config.ANTHROPIC_API_KEY)
                system_text = messages[0]["content"]
                user_messages = [m for m in messages if m["role"] != "system"]

                with client.messages.stream(
                    model=active_model,
                    system=system_text,
                    messages=user_messages,
                    temperature=config.LLM_TEMPERATURE,
                    max_tokens=config.LLM_MAX_TOKENS,
                ) as stream:
                    for text in stream.text_stream:
                        full_response += text
                        answer_placeholder.markdown(full_response + "▌")
                answer_placeholder.markdown(full_response)
                usage = stream.get_final_message().usage
                input_tokens = usage.input_tokens
                output_tokens = usage.output_tokens

            elif active_provider == "openai":
                from openai import OpenAI
                client = OpenAI(api_key=api_key or config.OPENAI_API_KEY)
                stream = client.chat.completions.create(
                    model=active_model,
                    messages=messages,
                    temperature=config.LLM_TEMPERATURE,
                    max_tokens=config.LLM_MAX_TOKENS,
                    stream=True,
                    stream_options={"include_usage": True},
                )
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        full_response += chunk.choices[0].delta.content
                        answer_placeholder.markdown(full_response + "▌")
                    if chunk.usage:
                        input_tokens = chunk.usage.prompt_tokens
                        output_tokens = chunk.usage.completion_tokens
                answer_placeholder.markdown(full_response)

            elif active_provider == "google":
                import google.generativeai as genai
                genai.configure(api_key=api_key or config.GOOGLE_API_KEY)
                gmodel = genai.GenerativeModel(active_model)
                prompt_text = "\n\n".join(m["content"] for m in messages)
                response = gmodel.generate_content(
                    prompt_text,
                    generation_config=genai.types.GenerationConfig(
                        temperature=config.LLM_TEMPERATURE,
                        max_output_tokens=config.LLM_MAX_TOKENS,
                    ),
                )
                full_response = response.text
                answer_placeholder.markdown(full_response)
                input_tokens = getattr(response.usage_metadata, "prompt_token_count", 0) if hasattr(response, "usage_metadata") else 0
                output_tokens = getattr(response.usage_metadata, "candidates_token_count", 0) if hasattr(response, "usage_metadata") else 0

        except Exception as e:
            st.error(f"LLM Error: {e}")
            full_response = f"Error: {e}"

        elapsed = int((time.time() - start_time) * 1000)

        # ── Step 5: Citations ──
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

        if citations:
            with st.expander("Sources", expanded=False):
                for c in citations:
                    st.caption(f"• {c['company']} ({c['ticker']}) — {c['filing_type']} {c['filing_date']}, {c['section']}")

        # Usage bar
        pipeline_data = {
            "chunks_retrieved": len(retrieval["chunks"]),
            "chunks_used": len(selected),
        }
        usage_data = {
            "provider": active_provider,
            "model": active_model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": elapsed,
        }
        st.caption(
            f"{active_provider}/{active_model} · "
            f"{len(retrieval['chunks'])}→{len(selected)} chunks · "
            f"{input_tokens:,}+{output_tokens:,} tokens · "
            f"{elapsed/1000:.1f}s"
        )

        if verbose:
            with pipeline_container:
                st.markdown("**[5] Result**")
                st.code(f"Input tokens: {input_tokens:,}\n"
                        f"Output tokens: {output_tokens:,}\n"
                        f"Latency: {elapsed:,}ms")

        # ── Step 6: Audit log ──
        log_query(
            user_id=user.name,
            user_role=user.role,
            query_text=prompt,
            chunks_retrieved=[c["id"] for c in selected],
            chunks_used=len(selected),
            llm_provider=active_provider,
            llm_model=active_model,
            response_text=full_response,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=elapsed,
        )

        # Save to chat history
        st.session_state.messages.append({
            "role": "assistant",
            "content": full_response,
            "citations": citations,
            "pipeline": pipeline_data,
            "usage": usage_data,
        })
