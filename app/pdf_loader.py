"""PDF loading and page-level text extraction."""

from __future__ import annotations

from pathlib import Path

import pymupdf

from app.models import PdfDocument, PdfPage


def load_pdf(pdf_path: str | Path) -> PdfDocument:
    """Load a PDF and extract text from each page.

    Page numbers are one-based and match the order used in the paper.
    """
    source = Path(pdf_path).expanduser().resolve()

    if not source.exists():
        raise FileNotFoundError(f"PDF not found: {source}")

    if not source.is_file():
        raise ValueError(f"PDF path is not a file: {source}")

    pages: list[PdfPage] = []
    warnings: list[str] = []

    with pymupdf.open(source) as document:
        raw_metadata = document.metadata or {}
        metadata = {
            str(key): str(value)
            for key, value in raw_metadata.items()
            if value not in (None, "")
        }

        for page_index, page in enumerate(document, start=1):
            text = (page.get_text("text") or "").strip()
            pages.append(PdfPage(page_number=page_index, text=text))

            if not text:
                warnings.append(
                    f"Page {page_index} has no extractable text; "
                    "the page may be scanned or image-only."
                )

        return PdfDocument(
            path=str(source),
            page_count=document.page_count,
            metadata=metadata,
            pages=pages,
            warnings=warnings,
        )