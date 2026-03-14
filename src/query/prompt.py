"""
Prompt template construction for SEC filing RAG.

Builds the system prompt and user message that go to the LLM.
The prompt enforces:
  - Grounding: only answer from the provided context
  - Citations: reference specific filings and sections
  - Structure: organized response with clear sections
  - Honesty: say "I don't have enough information" when context is insufficient
"""


SYSTEM_PROMPT = """You are a financial research assistant with access to SEC filing data (10-K and 10-Q reports). Your job is to answer questions accurately using ONLY the provided filing excerpts.

Rules:
1. ONLY use information from the provided context. Do not use outside knowledge.
2. CITE every claim with the source filing: [Company, Filing Type, Date, Section].
3. If the context doesn't contain enough information to answer, say so clearly.
4. When comparing multiple companies, organize your response with clear headings per company.
5. Include specific numbers, dates, and direct quotes when they add value.
6. Note the filing date for temporal context — older filings may not reflect current state.

Style:
- Be concise. Aim for 300-500 words total unless the question demands more.
- Use bullet points, not long paragraphs.
- Lead with the key insight, then support with evidence.
- One short quote per major point is sufficient — do not quote extensively."""


def build_prompt(query: str, chunks: list[dict]) -> list[dict]:
    """
    Build the messages array for the LLM call.

    Args:
        query: The user's question
        chunks: Retrieved chunks, each with 'text' and 'metadata'

    Returns:
        List of message dicts ready for the LLM API call.
    """
    # Format context from retrieved chunks
    context_parts = []
    for i, chunk in enumerate(chunks, 1):
        meta = chunk["metadata"]
        header = (
            f"[Source {i}: {meta['ticker']} | {meta['filing_type']} | "
            f"{meta['filing_date']} | {meta['section_name']}]"
        )
        context_parts.append(f"{header}\n{chunk['text']}")

    context = "\n\n---\n\n".join(context_parts)

    user_message = f"""Based on the following SEC filing excerpts, answer this question:

**Question:** {query}

**Filing Excerpts ({len(chunks)} sources):**

{context}"""

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message},
    ]
