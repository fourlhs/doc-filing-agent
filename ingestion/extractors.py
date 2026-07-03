"""Extraction strategies: Path -> DocumentContent.

v1 is the PDF text layer. To add OCR or vision later, write another function
matching ``Extractor`` and pass it to ``reader.load_document`` — nothing else
in the pipeline changes.
"""

from pathlib import Path
from typing import Callable

from pypdf import PdfReader

from agent.schema import DocumentContent

Extractor = Callable[[Path], DocumentContent]


def extract_text_layer(path: Path) -> DocumentContent:
    """Extract the PDF's text layer.

    A pure scan (no text layer) yields empty text — ``content.is_empty``,
    which downstream routes to review; that case never raises. Corrupt files
    and PDFs needing a real password DO raise (pypdf errors); main.py's
    per-document isolation owns those.
    """
    reader = PdfReader(path)
    if reader.is_encrypted:
        # Empty-password encryption is common; a real password surfaces as
        # FileNotDecryptedError at page access below.
        reader.decrypt("")
    page_texts = (page.extract_text().strip() for page in reader.pages)
    return DocumentContent(text="\n\n".join(t for t in page_texts if t))
