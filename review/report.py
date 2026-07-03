"""Write the human-readable CSV report of every processed document."""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from agent.schema import Decision
from routing.router import RoutingResult

# Column order chosen for a human scanning the file: identity first, the
# proposal, then the numbers, then the flag that says whether to look closer.
REVIEW_CSV_COLUMNS = [
    "doc_id",
    "source_name",
    "company",
    "doc_type",
    "date",
    "summary",
    "proposed_filename",
    "proposed_folder",
    "confidence_company",
    "confidence_doc_type",
    "confidence_date",
    "flag",  # auto | review
    "reason",
    "rationale",
    "parse_errors",  # entries joined with "; " — non-empty means the parser repaired fields
]


@dataclass(frozen=True)
class ReviewRow:
    """Everything the report needs about one document, already computed."""

    doc_id: str
    source_name: str
    decision: Decision
    routing: RoutingResult


def write_review_csv(rows: Iterable[ReviewRow], out_path: Path) -> None:
    """Serialize all rows to ``out_path`` using REVIEW_CSV_COLUMNS.

    TODO: implement after design review.
        - utf-8-sig encoding so Greek text opens cleanly in Excel
        - empty string for null dates
    """
    raise NotImplementedError("Skeleton only — pending design review")
