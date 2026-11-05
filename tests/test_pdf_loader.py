from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from app.pdf_loader import load_pdf


def _create_pdf(path: Path) -> None:
    document = pymupdf.open()

    page_one = document.new_page()
    page_one.insert_text((72, 72), "First page: experimental setup.")

    page_two = document.new_page()
    page_two.insert_text((72, 72), "Second page: results and discussion.")

    document.save(path)
    document.close()


def test_load_pdf_preserves_page_numbers(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    _create_pdf(pdf_path)

    document = load_pdf(pdf_path)

    assert document.page_count == 2
    assert [page.page_number for page in document.pages] == [1, 2]
    assert "experimental setup" in document.pages[0].text
    assert "results and discussion" in document.pages[1].text
    assert document.warnings == []


def test_load_pdf_reports_empty_pages(tmp_path: Path) -> None:
    pdf_path = tmp_path / "blank.pdf"

    document = pymupdf.open()
    document.new_page()
    document.save(pdf_path)
    document.close()

    result = load_pdf(pdf_path)

    assert result.page_count == 1
    assert result.pages[0].text == ""
    assert len(result.warnings) == 1
    assert "Page 1" in result.warnings[0]


def test_load_pdf_rejects_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "missing.pdf"

    with pytest.raises(FileNotFoundError):
        load_pdf(missing)