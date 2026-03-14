"""
SEC filing preprocessor: metadata extraction, XBRL stripping, section parsing.

This is the foundation of data quality for the entire RAG pipeline. Every metadata
field extracted here becomes a filter dimension in retrieval — wrong metadata means
wrong search results, regardless of how good the embeddings are.

Corpus format (all 246 files):
  Lines 1-7+: Structured header (Company, Ticker, Filing Type, Filing Date, etc.)
  Line after header: "====" separator
  Next 1-2 lines: XBRL blob (machine-readable financial data, useless for NLP)
  Remaining: Human-readable filing text starting with cover page

Design decisions:
  - We parse metadata from the header, NOT from the filing text. The header is
    structured and consistent across all 246 files. Parsing from text would require
    company-specific heuristics.
  - XBRL stripping uses multiple heuristics (not just "UNITED STATES") because
    2 of 246 files don't contain that marker. We fall back to line-length analysis.
  - Section extraction is case-insensitive and handles both "Item 1A." and
    "ITEM 1A." formats. We distinguish TOC entries from actual content sections
    by checking for page-number patterns.
"""

import re
import hashlib
from pathlib import Path
from dataclasses import dataclass, field

import config


@dataclass
class FilingMetadata:
    """Metadata parsed from a filing's header."""
    company_name: str
    ticker: str
    filing_type: str       # "10-K" or "10-Q"
    filing_date: str       # YYYY-MM-DD
    report_period: str     # YYYY-MM-DD or "" if not present
    quarter: str           # e.g., "2024Q3" or "" if not present
    cik: str
    source_url: str
    source_file: str


@dataclass
class Section:
    """A single extracted section from a filing."""
    name: str              # e.g., "Risk Factors", "Business"
    item_number: str       # e.g., "1A", "7"
    text: str              # Full section text
    part: str              # "Part I", "Part II", etc.
    source_hash: str = ""  # SHA-256 of section text for data integrity


@dataclass
class ParsedFiling:
    """Complete parsed output for a single filing."""
    metadata: FilingMetadata
    sections: list[Section] = field(default_factory=list)
    full_text: str = ""    # All text after XBRL stripping (for fallback)


# ── Section name extraction ───────────────────────────────────────────────────
# Instead of hardcoding section names, we parse them from each filing's own
# Table of Contents. Every SEC filing includes a TOC that maps Item numbers
# to section titles. This means:
#   - Zero hardcoded mappings to maintain
#   - Automatically adapts when the SEC adds new items (e.g., Item 1C in 2023)
#   - Handles company-specific title variations
#   - Each filing is self-describing

# Regex for section headings: "Item 1A." or "ITEM 1A." or "Item 1 —" or "Item 1 |"
# The period after the item number is optional — JNJ uses "Item 1 |" without periods
_ITEM_PATTERN = re.compile(
    r"^(ITEM|Item)\s+(\d+[A-C]?)\.?\s*[—\|.]?\s*(.*)",
    re.IGNORECASE,
)

# Regex for Part headings
_PART_PATTERN = re.compile(
    r"^(PART|Part)\s+(I{1,3}V?|[1-4])\b",
    re.IGNORECASE,
)


def _build_toc_map(text: str) -> dict[str, str]:
    """
    Build a mapping of Item numbers to section names from the filing's TOC.

    Parses short TOC entries like:
      "Item 1. | Business | 1"
      "ITEM 1A. RISK FACTORS | 15"
      "Item 1 |  | Financial statements (unaudited) | 1"

    Returns:
        {"1": "Business", "1A": "Risk Factors", "7": "MD&A", ...}
    """
    toc_map = {}
    for line in text.split("\n"):
        # Only consider short lines (TOC entries, not content)
        if len(line) > 200:
            continue

        match = _ITEM_PATTERN.match(line.strip())
        if not match:
            continue

        # Must end with a page number or N/A to be a TOC entry
        if not re.search(r"\|\s*(\d+[-–]\d+|\d+|N/A)\s*$", line):
            continue

        item_num = match.group(2).upper()
        title_raw = match.group(3).strip()

        # Extract clean title: handle "| Business | 1" and "BUSINESS | 3" formats
        # Remove page number at end
        title_raw = re.sub(r"\|\s*(\d+[-–]\d+|\d+|N/A)\s*$", "", title_raw).strip()
        # Remove leading/trailing pipes
        title_raw = title_raw.strip("|").strip()
        # Remove internal pipes (some formats use "| Business |")
        if "|" in title_raw:
            # Take the longest pipe-separated segment as the title
            parts = [p.strip() for p in title_raw.split("|") if p.strip()]
            title_raw = max(parts, key=len) if parts else title_raw

        # Clean up: title case, remove brackets like [Reserved]
        title = title_raw.strip()
        if title:
            # Normalize to title case if all-caps
            if title == title.upper() and len(title) > 3:
                title = title.title()
            toc_map[item_num] = title

    return toc_map


def parse_header(lines: list[str], filename: str) -> FilingMetadata:
    """
    Parse the structured metadata header from the first lines of a filing.

    The header format is consistent across all 246 files:
      Company: <name>
      Ticker: <ticker>
      Filing Type: <type>
      Filing Date: <date>
      [Report Period: <date>]   # present in ~192/246 files
      [Quarter: <quarter>]      # present in ~192/246 files
      CIK: <cik>
      Source: SEC EDGAR
      URL: <url>
    """
    header = {}
    for line in lines:
        if line.startswith("===="):
            break
        if ":" in line:
            key, _, value = line.partition(":")
            header[key.strip()] = value.strip()

    # Normalize filing type: "10-K (Annual Report)" → "10-K"
    filing_type_raw = header.get("Filing Type", "")
    filing_type = "10-K" if "10-K" in filing_type_raw else "10-Q"

    return FilingMetadata(
        company_name=header.get("Company", ""),
        ticker=header.get("Ticker", "").upper(),
        filing_type=filing_type,
        filing_date=header.get("Filing Date", ""),
        report_period=header.get("Report Period", ""),
        quarter=header.get("Quarter", ""),
        cik=header.get("CIK", ""),
        source_url=header.get("URL", ""),
        source_file=filename,
    )


def strip_xbrl(text: str) -> str:
    """
    Remove the XBRL blob and return only human-readable filing text.

    Strategy (ordered by reliability):
    1. Find "UNITED STATES" (works for 244/246 files) — this is the standard
       cover page header for SEC filings
    2. Fall back to finding "FORM 10-K" or "FORM 10-Q" markers
    3. Last resort: find the first line after the separator that looks like
       normal text (< 1000 chars, contains spaces)

    We deliberately use multiple heuristics because a production system can't
    fail silently on 2 out of 246 files.
    """
    # Strategy 1: "UNITED STATES" marker (most common)
    idx = text.find("UNITED STATES")
    if idx != -1:
        return text[idx:]

    # Strategy 2: Form type markers
    for marker in ["FORM 10-K", "FORM 10-Q", "Form 10-K", "Form 10-Q"]:
        idx = text.find(marker)
        if idx != -1:
            # Back up to start of line
            line_start = text.rfind("\n", 0, idx)
            return text[line_start + 1 if line_start != -1 else idx:]

    # Strategy 3: First readable line after XBRL
    lines = text.split("\n")
    for i, line in enumerate(lines):
        # Skip short lines and XBRL-like content (very long, no spaces)
        if len(line) > 20 and len(line) < 1000 and " " in line:
            # Check it's not still XBRL (contains http:// or fasb.org patterns)
            if "fasb.org" not in line and "xbrli:" not in line:
                return "\n".join(lines[i:])

    # If all else fails, return everything after the separator
    sep_idx = text.find("=" * 10)
    if sep_idx != -1:
        return text[sep_idx + text[sep_idx:].find("\n") + 1:]

    return text


def _is_toc_entry(line: str) -> bool:
    """
    Distinguish Table of Contents entries from actual section headings.

    TOC entries are short lines with page numbers: "Item 1A. | Risk Factors | 5"
    Content sections are long (thousands of chars) and may coincidentally end
    with page number footers like "Apple Inc. | 2025 Form 10-K | 4".

    Key heuristic: TOC entries are short (< 200 chars). A real content section
    starting with "Item 1A." will be thousands of characters long because the
    entire section text follows on the same line.
    """
    return len(line) < 200 and bool(re.search(r"\|\s*(\d+[-–]\d+|\d+|N/A)\s*$", line))


def _normalize_text(text: str) -> str:
    """
    Normalize filing text so section headings appear at the start of lines.

    Many filings (especially newer ones) have Item headings embedded mid-line:
      "...employee retention.Item 1B.    Unresolved Staff Comments..."

    We insert line breaks before Item and Part headings so the section
    extraction logic can find them reliably. Also normalizes Part headings
    that appear mid-line like "...PART IIITEM 5.".
    """
    # Insert newline before "Item X." or "ITEM X." or "Item X —" when preceded by non-whitespace
    text = re.sub(r"(?<=[^\n])((?:ITEM|Item)\s+\d+[A-C]?[.\s])", r"\n\1", text)
    # Insert newline before "PART I" / "Part II" etc. when preceded by non-whitespace
    text = re.sub(r"(?<=[^\n])((?:PART|Part)\s+I{1,3}V?(?:\s|[.\-]))", r"\n\1", text)
    return text


def _finalize_section(name: str, item_number: str, lines: list[str], part: str) -> Section | None:
    """Create a Section from accumulated lines, or None if too short.

    Filters out spurious sections created by inline references like
    "discussed in Item 1A of this Form" that get split onto their own lines.
    Real sections are at least MIN_CHUNK_SIZE characters.
    """
    text = "\n".join(lines).strip()
    if not text or len(text) < config.MIN_CHUNK_SIZE:
        return None
    return Section(
        name=name,
        item_number=item_number,
        text=text,
        part=part,
        source_hash=hashlib.sha256(text.encode()).hexdigest(),
    )


def _strip_title_from_content(content: str, toc_map: dict[str, str], current_name: str) -> str:
    """
    Remove the section title prefix from inline content.

    When a heading like "Item 1.    BusinessCompany Background..." appears,
    we need to strip "Business" to get just the content text.
    """
    # Try removing the TOC-derived name with optional pipe separators
    stripped = re.sub(r"^\|?\s*" + re.escape(current_name) + r"\s*\|?\s*", "", content, count=1)
    if stripped != content:
        return stripped.strip()

    # Fall back to trying all known titles from this filing's TOC
    for title in toc_map.values():
        if content.startswith(title):
            return content[len(title):].strip()

    return content.strip()


def extract_sections(text: str, filing_type: str) -> list[Section]:
    """
    Extract sections from filing text using Item number headings.

    Handles:
    - Case variations: "Item 1A." and "ITEM 1A."
    - Separator variations: "Item 1. | Business" and "Item 1.Business"
    - Mid-line headings: normalizes text so headings start on their own line
    - TOC vs content: skips Table of Contents entries (have page numbers)
    - Part tracking: maintains current Part (I, II, III, IV) for 10-Q context
    - Duplicate Item numbers: 10-Q has Item 1 in both Part I and Part II

    Returns sections ordered as they appear in the filing.
    """
    # Build section name map from the filing's own TOC
    toc_map = _build_toc_map(text)

    # Normalize so headings are at line starts
    text = _normalize_text(text)
    lines = text.split("\n")
    sections = []
    current_part = ""
    current_item = None
    current_name = ""
    current_lines = []

    for line in lines:
        # Track Part headings
        part_match = _PART_PATTERN.match(line.strip())
        if part_match:
            part_num = part_match.group(2).upper()
            roman_map = {"1": "I", "2": "II", "3": "III", "4": "IV"}
            current_part = f"Part {roman_map.get(part_num, part_num)}"
            continue

        # Check for Item headings
        item_match = _ITEM_PATTERN.match(line.strip())
        if item_match:
            if _is_toc_entry(line):
                continue

            # Save previous section
            if current_item is not None:
                section = _finalize_section(current_name, current_item, current_lines, current_part)
                if section:
                    sections.append(section)

            # Start new section
            current_item = item_match.group(2).upper()
            current_name = toc_map.get(current_item, f"Item {current_item}")

            # Extract inline content from the heading line
            after_item = item_match.group(3).strip()
            content = _strip_title_from_content(after_item, toc_map, current_name)
            current_lines = [content] if content else []
            continue

        # Accumulate lines for current section
        if current_item is not None:
            current_lines.append(line)

    # Save the last section
    if current_item is not None:
        section = _finalize_section(current_name, current_item, current_lines, current_part)
        if section:
            sections.append(section)

    return sections


def parse_filing(filepath: Path) -> ParsedFiling:
    """
    Parse a single SEC filing: extract metadata, strip XBRL, extract sections.

    This is the main entry point for preprocessing. Returns a ParsedFiling with
    structured metadata, clean section text, and integrity hashes.
    """
    raw_text = filepath.read_text(encoding="utf-8", errors="replace")
    lines = raw_text.split("\n")

    # Parse header metadata
    metadata = parse_header(lines, filepath.name)

    # Strip XBRL — find where the separator is, take everything after
    sep_idx = raw_text.find("=" * 10)
    if sep_idx != -1:
        after_header = raw_text[sep_idx + raw_text[sep_idx:].find("\n") + 1:]
    else:
        after_header = raw_text

    # Strip XBRL from post-header content
    clean_text = strip_xbrl(after_header)

    # Extract sections
    sections = extract_sections(clean_text, metadata.filing_type)

    return ParsedFiling(
        metadata=metadata,
        sections=sections,
        full_text=clean_text,
    )


def parse_corpus(corpus_dir: Path | None = None) -> list[ParsedFiling]:
    """
    Parse all filings in the corpus directory.

    Args:
        corpus_dir: Path to directory containing .txt filing files.
                    Defaults to config.CORPUS_DIR.

    Returns:
        List of ParsedFiling objects, one per file.
    """
    corpus_dir = corpus_dir or config.CORPUS_DIR
    filings = []
    txt_files = sorted(corpus_dir.glob("*.txt"))

    print(f"Parsing {len(txt_files)} filings from {corpus_dir}...")

    for i, filepath in enumerate(txt_files):
        try:
            filing = parse_filing(filepath)
            filings.append(filing)
            if (i + 1) % 50 == 0:
                print(f"  Parsed {i + 1}/{len(txt_files)} filings...")
        except Exception as e:
            print(f"  WARNING: Failed to parse {filepath.name}: {e}")

    # Summary stats
    total_sections = sum(len(f.sections) for f in filings)
    tickers = set(f.metadata.ticker for f in filings)
    print(f"  Done: {len(filings)} filings, {total_sections} sections, {len(tickers)} companies")

    return filings
