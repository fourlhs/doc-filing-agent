"""Read documents from the local input/ folder and extract their content.

Boundary contract: everything downstream sees only ``RawDocument``. To move
the input source to cloud storage later, reimplement this module — the rest
of the pipeline is untouched.

Two functions instead of one generator so main.py can isolate failures per
document (a generator that raises mid-iteration would kill the whole run).
"""

from dataclasses import dataclass
from pathlib import Path

from agent.schema import DocumentContent
from ingestion.extractors import Extractor, extract_text_layer


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


def list_documents(input_dir: Path) -> tuple[list[Path], list[Path]]:
    """Return (documents, skipped): sorted PDFs to process, plus everything
    else found (wrong-format files, stray directories), so main.py can log
    the latter instead of silently ignoring something a person dropped in."""
    docs: list[Path] = []
    skipped: list[Path] = []
    for entry in sorted(input_dir.iterdir()):
        if entry.name == ".gitkeep":
            continue
        if entry.is_file() and entry.suffix.lower() == ".pdf":
            docs.append(entry)
        else:
            skipped.append(entry)
    return docs, skipped


def load_document(path: Path, extract: Extractor = extract_text_layer) -> RawDocument:
    """Extract one document. May raise on corrupt/unreadable files —
    main.py isolates failures per document.

    doc_id = filename: human-friendly, and it is the join key between the
    ground-truth CSV (eval/) and the review report.
    """
    return RawDocument(doc_id=path.name, source_name=path.name, content=extract(path))
