#!/usr/bin/env python3
"""
CLI entry point for querying SEC filings.

Standard mode: clean answer with citations and usage stats.
Verbose mode (-v): full pipeline transparency — query parsing, retrieval
filters, chunk rankings, prompt token count, LLM call details.

Usage:
    python scripts/query.py                          # interactive setup
    python scripts/query.py --role admin             # skip role picker
    python scripts/query.py --role admin -v          # verbose mode
"""

import readline  # noqa: F401 — enables arrow keys and line editing in input()
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pick import pick
from src.query.rag import ask
from src.enterprise.auth import get_user, describe_access, DEMO_USERS


def _parse_args():
    """Parse CLI flags, return (role, verbose)."""
    role = None
    verbose = False
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] in ("-v", "--verbose"):
            verbose = True
        elif args[i] == "--role" and i + 1 < len(args):
            role = args[i + 1]
            i += 1
        i += 1
    return role, verbose


def _pick_role() -> str:
    """Arrow-key role selector."""
    options = []
    keys = []
    for uid, user in DEMO_USERS.items():
        options.append(f"{uid:20s} {describe_access(user)}")
        keys.append(uid)

    _, idx = pick(options, "Select your role (↑↓ then Enter):", indicator="→")
    return keys[idx]


def _pick_mode() -> bool:
    """Arrow-key mode selector."""
    options = [
        "Standard    — answer with citations",
        "Verbose     — full pipeline details (parsing, retrieval, tokens)",
    ]
    _, idx = pick(options, "Select output mode (↑↓ then Enter):", indicator="→")
    return idx == 1


def main():
    role_arg, verbose_arg = _parse_args()

    print("=" * 60)
    print("  SEC Filing Research Tool — CLI")
    print("=" * 60)

    # Role selection: CLI flag or interactive picker
    if role_arg:
        user_id = role_arg
    else:
        user_id = _pick_role()
    user = get_user(user_id)

    # Mode selection: CLI flag or interactive picker
    if verbose_arg:
        verbose = True
    elif role_arg:
        # If role was passed via flag, don't prompt for mode — default standard
        verbose = False
    else:
        verbose = _pick_mode()

    print(f"\n→ {user.name} ({describe_access(user)})")
    if verbose:
        print("  Mode: verbose (full pipeline)")
    print("  Ctrl+C to exit\n")

    # Query loop
    while True:
        try:
            query = input("Ask a question: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n")
            break

        if not query:
            continue

        result = ask(query, user, verbose=verbose, stream=True)

        # If streaming failed (e.g., rate limit), the answer wasn't printed — show it
        u = result.get("usage", {})
        if u.get("input_tokens", 0) == 0 and u.get("output_tokens", 0) == 0 and result.get("answer"):
            print(f"\n{result['answer']}")

        # Print citations
        if result["citations"]:
            print(f"\n{'─' * 60}")
            print("Sources:")
            for c in result["citations"]:
                print(f"  • {c['company']} ({c['ticker']}) — {c['filing_type']} {c['filing_date']}, {c['section']}")

        # Print usage summary
        u = result["usage"]
        p = result["pipeline"]
        if u.get("input_tokens"):
            if verbose:
                print(f"\n{'─' * 60}")
                print(f"  Chunks: {p['chunks_retrieved']} retrieved → {p['chunks_used']} used")
                print(f"  Tokens: {u['input_tokens']:,} in / {u['output_tokens']:,} out")
                print(f"  Model:  {u.get('provider', '?')}/{u.get('model', '?')}")
                print(f"  Latency: {u['latency_ms']:,}ms")
            else:
                print(f"\n[{u.get('provider', '?')}/{u.get('model', '?')} · {u['latency_ms']/1000:.1f}s]")
        print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n")
    except EOFError:
        print("\n")
