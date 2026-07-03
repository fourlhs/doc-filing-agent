"""Tests for ingestion: text-layer extraction and document listing.

Fixture PDFs in tests/fixtures/ were generated once (Greek text via an
embedded TTF; see docs/ROADMAP.md step 2) and are committed as binaries.
"""

from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.errors import PdfReadError

from ingestion.extractors import extract_text_layer
from ingestion.reader import list_documents, load_document

FIXTURES = Path(__file__).parent / "fixtures"


def encrypted_copy(tmp_path: Path, user_password: str) -> Path:
    writer = PdfWriter(clone_from=FIXTURES / "greek_text.pdf")
    writer.encrypt(user_password=user_password, owner_password="owner", algorithm="AES-256")
    out = tmp_path / "encrypted.pdf"
    writer.write(out)
    return out


def test_text_layer_extracts_greek_across_pages():
    content = extract_text_layer(FIXTURES / "greek_text.pdf")
    assert "ΤΙΜΟΛΟΓΙΟ ΠΩΛΗΣΗΣ" in content.text
    assert "Helector" in content.text
    assert "Σελίδα 2" in content.text  # page 2 present, pages joined
    assert not content.is_empty


def test_pdf_without_text_layer_yields_empty_content_not_exception():
    content = extract_text_layer(FIXTURES / "no_text_layer.pdf")
    assert content.text == ""
    assert content.is_empty


def test_corrupt_file_raises_for_main_to_isolate(tmp_path):
    fake = tmp_path / "fake.pdf"
    fake.write_bytes(b"this is definitely not a pdf")
    with pytest.raises(PdfReadError):
        extract_text_layer(fake)


def test_empty_password_encrypted_pdf_extracts(tmp_path):
    content = extract_text_layer(encrypted_copy(tmp_path, user_password=""))
    assert "ΤΙΜΟΛΟΓΙΟ ΠΩΛΗΣΗΣ" in content.text


def test_password_protected_pdf_raises_for_main_to_isolate(tmp_path):
    with pytest.raises(PdfReadError):  # FileNotDecryptedError at page access
        extract_text_layer(encrypted_copy(tmp_path, user_password="secret"))


def test_list_documents_filters_and_sorts(tmp_path):
    for name in ("b.pdf", "A.PDF", "note.txt", ".gitkeep"):
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "subdir").mkdir()
    docs, skipped = list_documents(tmp_path)
    assert [p.name for p in docs] == ["A.PDF", "b.pdf"]
    assert [p.name for p in skipped] == ["note.txt", "subdir"]


def test_load_document_uses_filename_as_doc_id():
    raw = load_document(FIXTURES / "greek_text.pdf")
    assert raw.doc_id == "greek_text.pdf"
    assert raw.source_name == "greek_text.pdf"
    assert not raw.content.is_empty
