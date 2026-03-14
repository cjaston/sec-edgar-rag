"""
Role-based access control for SEC filing queries.

Defines user roles and translates them into ChromaDB metadata filters.
Access control is enforced at the database layer — restricted chunks never
enter search results, they're excluded before semantic similarity runs.

Demo roles:
  - admin: Full access to all filings, all companies, all sectors
  - analyst: Access to assigned sectors only (configurable per user)
  - restricted: Public-access filings only

In production, user identity would come from SSO/OAuth. Here, the user
selects their role in the CLI or Streamlit UI to demonstrate the feature.
"""

from dataclasses import dataclass, field

import config


@dataclass
class User:
    """A user with a role and access permissions."""
    name: str
    role: str                          # "admin", "analyst", "restricted"
    allowed_sectors: list[str] = field(default_factory=list)   # For analyst role
    allowed_tickers: list[str] = field(default_factory=list)   # Optional: specific companies
    tenant_id: str = ""


# Demo users for testing access control
DEMO_USERS = {
    "admin": User(
        name="Admin User",
        role="admin",
        tenant_id=config.DEFAULT_TENANT_ID,
    ),
    "tech_analyst": User(
        name="Tech Sector Analyst",
        role="analyst",
        allowed_sectors=["tech"],
        tenant_id=config.DEFAULT_TENANT_ID,
    ),
    "finance_analyst": User(
        name="Finance Sector Analyst",
        role="analyst",
        allowed_sectors=["finance"],
        tenant_id=config.DEFAULT_TENANT_ID,
    ),
    "pharma_analyst": User(
        name="Pharma Sector Analyst",
        role="analyst",
        allowed_sectors=["pharma"],
        tenant_id=config.DEFAULT_TENANT_ID,
    ),
    "restricted": User(
        name="Restricted User",
        role="restricted",
        tenant_id=config.DEFAULT_TENANT_ID,
    ),
}


def get_user(user_id: str) -> User:
    """Look up a demo user by ID. Returns admin if not found."""
    return DEMO_USERS.get(user_id, DEMO_USERS["admin"])


def get_access_filter(user: User) -> dict | None:
    """
    Build a ChromaDB 'where' clause that enforces this user's access level.

    Returns None for admin (no filter needed — sees everything).
    Returns a dict for other roles that ChromaDB uses to exclude chunks
    before semantic search.

    Examples:
      admin     → None (no filter)
      analyst   → {"sector": {"$in": ["tech"]}}
      restricted → {"access_level": "public"}
    """
    if user.role == "admin":
        return None

    if user.role == "restricted":
        return {"access_level": "public"}

    if user.role == "analyst":
        conditions = []

        if user.allowed_sectors:
            if len(user.allowed_sectors) == 1:
                conditions.append({"sector": user.allowed_sectors[0]})
            else:
                conditions.append({"sector": {"$in": user.allowed_sectors}})

        if user.allowed_tickers:
            if len(user.allowed_tickers) == 1:
                conditions.append({"ticker": user.allowed_tickers[0]})
            else:
                conditions.append({"ticker": {"$in": user.allowed_tickers}})

        if not conditions:
            return None
        if len(conditions) == 1:
            return conditions[0]
        # ChromaDB requires $and for combining multiple filter conditions
        return {"$and": conditions}

    return None


def check_access(user: User, chunk_metadata: dict) -> bool:
    """
    Check if a user can access a specific chunk. Used for post-retrieval
    verification and UI display (e.g., showing "access denied" messages).
    """
    if user.role == "admin":
        return True

    if user.role == "restricted":
        return chunk_metadata.get("access_level") == "public"

    if user.role == "analyst":
        if user.allowed_sectors:
            if chunk_metadata.get("sector") not in user.allowed_sectors:
                return False
        if user.allowed_tickers:
            if chunk_metadata.get("ticker") not in user.allowed_tickers:
                return False
        return True

    return False


def describe_access(user: User) -> str:
    """Human-readable description of what this user can see."""
    if user.role == "admin":
        return "Full access — all companies, all sectors, all filings"
    if user.role == "restricted":
        return "Public filings only"
    if user.role == "analyst":
        parts = []
        if user.allowed_sectors:
            parts.append(f"sectors: {', '.join(user.allowed_sectors)}")
        if user.allowed_tickers:
            parts.append(f"tickers: {', '.join(user.allowed_tickers)}")
        return f"Analyst access — {'; '.join(parts)}" if parts else "Analyst access — no restrictions"
    return "Unknown role"
