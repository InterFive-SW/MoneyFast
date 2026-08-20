# filename: chunking.py
"""Document splitting for ingestion.

Deliberately simple: paragraph boundaries first, then a hard character window
for any paragraph that overruns. A sentence-aware splitter would need a
Turkish sentence model, and the corpus (company profiles, activity reports,
KAP disclosures) is already paragraph-structured, so the extra dependency
would buy very little.

The overlap exists so a fact spanning a boundary is retrievable from either
side; without it, the sentence that happens to straddle the split is the one
that never matches.
"""

from __future__ import annotations

import re

DEFAULT_MAX_CHARS = 1200
DEFAULT_OVERLAP = 150

_PARAGRAPH = re.compile(r"\n\s*\n")


def split(text: str, max_chars: int = DEFAULT_MAX_CHARS, overlap: int = DEFAULT_OVERLAP) -> list[str]:
    if overlap >= max_chars:
        raise ValueError("overlap must be smaller than max_chars")

    chunks: list[str] = []
    buffer = ""

    for paragraph in _PARAGRAPH.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(buffer) + len(paragraph) + 2 <= max_chars:
            buffer = f"{buffer}\n\n{paragraph}" if buffer else paragraph
            continue
        if buffer:
            chunks.append(buffer)
            buffer = ""
        if len(paragraph) <= max_chars:
            buffer = paragraph
            continue
        # One oversized paragraph, cut into overlapping windows.
        start = 0
        while start < len(paragraph):
            chunks.append(paragraph[start : start + max_chars])
            start += max_chars - overlap

    if buffer:
        chunks.append(buffer)
    return [chunk.strip() for chunk in chunks if chunk.strip()]
