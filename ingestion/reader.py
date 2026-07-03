"""Read documents from the local input/ folder and extract their content.

Boundary contract: everything downstream sees only ``RawDocument``. To move
the input source to cloud storage later, reimplement ``iter_documents`` — the
rest of the pipeline is untouched.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from agent.schema import DocumentContent


@dataclass(frozen=True)
class RawDocument:
    """A document as handed to the rest of the pipeline.

    doc_id:      stable identifier for this document (used to join with
                 ground truth in eval/ and rows in review/).
    source_name: original filename, kept for the human-readable report.
    content:     extracted content (text and/or page images), no
                 interpretation applied.
    """

    doc_id: str
    source_name: str
    content: DocumentContent


def iter_documents(input_dir: Path) -> Iterator[RawDocument]:
    """Yield a ``RawDocument`` for every document found in ``input_dir``.

    TODO: implement after design review.
        - which extensions to accept (.pdf, .png, .jpg, .tiff?)
        - doc_id scheme (filename stem? content hash?)
        - error handling for unreadable/corrupt files
    """
    raise NotImplementedError("Skeleton only — pending design review")


def extract_text(path: Path) -> DocumentContent:
    """Extract content from one printed Greek document.

    v1 (per docs/ROADMAP.md step 2): pypdf text layer. OCR/vision extractors
    can be added later as alternative implementations filling the same
    DocumentContent contract.
    Must extract only — no classification, no cleanup beyond whitespace.
    """
    raise NotImplementedError("Skeleton only — pending design review")
