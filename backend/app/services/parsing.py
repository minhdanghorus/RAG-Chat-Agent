"""Extract plain text from uploaded documents (PDF, DOCX, TXT)."""
from __future__ import annotations

import io

from pypdf import PdfReader

# Map of accepted content types -> logical format. Some browsers send odd MIME
# types, so callers may also fall back to the filename extension.
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


class UnsupportedDocumentError(ValueError):
    pass


def _extract_pdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)


def _extract_docx(data: bytes) -> str:
    from docx import Document as DocxDocument

    doc = DocxDocument(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)


def _extract_txt(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def extract_text(filename: str, data: bytes) -> str:
    """Extract text based on the file extension. Raises UnsupportedDocumentError."""
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return _extract_pdf(data)
    if lower.endswith(".docx"):
        return _extract_docx(data)
    if lower.endswith((".txt", ".md")):
        return _extract_txt(data)
    raise UnsupportedDocumentError(f"Unsupported file type: {filename}")


def is_supported(filename: str) -> bool:
    return any(filename.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS)
