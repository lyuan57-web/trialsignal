"""Deterministic normalization used before probabilistic entity resolution."""

from __future__ import annotations

import re
import unicodedata

_CORPORATE_SUFFIXES = {
    "ag",
    "co",
    "company",
    "corp",
    "corporation",
    "gmbh",
    "inc",
    "incorporated",
    "llc",
    "ltd",
    "limited",
    "plc",
    "sa",
}


def normalize_text(value: str | None) -> str:
    """Return an ASCII, case-folded, whitespace-normalized representation."""
    if not value:
        return ""
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    tokens = re.findall(r"[a-z0-9]+", ascii_value.casefold())
    return " ".join(tokens)


def normalize_sponsor(value: str | None) -> str:
    """Create a conservative sponsor blocking key.

    Corporate suffixes are removed, but no fuzzy merge is performed here. The
    original value is always retained in the warehouse for auditability.
    """
    tokens = normalize_text(value).split()
    while tokens and tokens[-1] in _CORPORATE_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)
