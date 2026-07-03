"""Read documents from the local input/ folder and extract their text.

Boundary contract: everything downstream sees only ``RawDocument``. To move
the input source to cloud storage later, reimplement ``iter_documents`` — the
rest of the pipeline is untouched.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class RawDocument:
    """A document as handed to the rest of the pipeline.

    doc_id:      stable identifier for this document (used to join with
                 ground truth in eval/ and rows in review/).
    source_name: original filename, kept for the human-readable report.
    text:        extracted plain text (Greek), no interpretation applied.
    """

    doc_id: str
    source_name: str
    text: str


def iter_documents(input_dir: Path) -> Iterator[RawDocument]:
    """Yield a ``RawDocument`` for every document found in ``input_dir``.

    TODO: implement after design review.
        - which extensions to accept (.pdf, .png, .jpg, .tiff?)
        - doc_id scheme (filename stem? content hash?)
        - error handling for unreadable/corrupt files
    """
    raise NotImplementedError("Skeleton only — pending design review")


def extract_text(path: Path) -> str:
    """Extract plain text from one printed Greek document.

    TODO: choose extraction method after inspecting real samples:
        - pypdf if PDFs carry a text layer
        - pdf2image + pytesseract (lang='ell') if they are pure scans
    Must return text only — no classification, no cleanup beyond whitespace.
    """
    raise NotImplementedError("Skeleton only — pending design review")
