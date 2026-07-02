"""Split text into overlapping chunks.

Self-contained recursive splitter: prefer to break on paragraph, then line,
then sentence, then word boundaries, keeping each chunk near the target size
with a fixed overlap for context continuity.
"""
from __future__ import annotations

DEFAULT_CHUNK_SIZE = 1200  # characters
DEFAULT_OVERLAP = 150

_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]


def _split_recursive(text: str, size: int, seps: list[str]) -> list[str]:
    if len(text) <= size:
        return [text]
    sep = seps[0] if seps else ""
    rest = seps[1:] if seps else []
    if sep == "":
        # Hard split by size as a last resort.
        return [text[i : i + size] for i in range(0, len(text), size)]

    parts = text.split(sep)
    chunks: list[str] = []
    current = ""
    for part in parts:
        piece = part + sep
        if len(current) + len(piece) <= size:
            current += piece
        else:
            if current:
                chunks.append(current)
            if len(piece) > size:
                chunks.extend(_split_recursive(part, size, rest))
                current = ""
            else:
                current = piece
    if current:
        chunks.append(current)
    return [c for c in chunks if c.strip()]


def _apply_overlap(chunks: list[str], overlap: int) -> list[str]:
    if overlap <= 0 or len(chunks) <= 1:
        return chunks
    out = [chunks[0]]
    for i in range(1, len(chunks)):
        tail = chunks[i - 1][-overlap:]
        out.append(tail + chunks[i])
    return out


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    text = text.strip()
    if not text:
        return []
    base = _split_recursive(text, chunk_size, _SEPARATORS)
    base = [c.strip() for c in base if c.strip()]
    return _apply_overlap(base, overlap)
