"""Write the human-readable CSV report of every processed document."""

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from agent.schema import Decision
from routing.router import RoutingResult

# utf-8-sig: the BOM makes Excel on Windows detect UTF-8, so Greek renders.
ENCODING = "utf-8-sig"
# Greek-locale Excel expects ';' out of the box — flip this constant if the
# report opens as one column (see CLAUDE.md).
DELIMITER = ","

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
    "agreement_company",  # sampling agreement — empty on single-sample runs
    "agreement_doc_type",
    "agreement_date",
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
    """Serialize all rows to ``out_path`` (overwriting it) — one report per run."""
    with out_path.open("w", encoding=ENCODING, newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=REVIEW_CSV_COLUMNS, delimiter=DELIMITER)
        writer.writeheader()
        for row in rows:
            writer.writerow(_serialize(row))


def _serialize(row: ReviewRow) -> dict[str, str]:
    decision = row.decision
    return {
        "doc_id": row.doc_id,
        "source_name": row.source_name,
        "company": decision.company.value,
        "doc_type": decision.doc_type.value,
        "date": decision.date.isoformat() if decision.date else "",
        "summary": decision.summary,
        "proposed_filename": decision.proposed_filename,
        "proposed_folder": decision.proposed_folder,
        "confidence_company": f"{decision.confidence.company:.2f}",
        "confidence_doc_type": f"{decision.confidence.doc_type:.2f}",
        "confidence_date": f"{decision.confidence.date:.2f}",
        "agreement_company": f"{decision.agreement.company:.2f}" if decision.agreement else "",
        "agreement_doc_type": f"{decision.agreement.doc_type:.2f}" if decision.agreement else "",
        "agreement_date": f"{decision.agreement.date:.2f}" if decision.agreement else "",
        "flag": row.routing.destination.value,
        "reason": row.routing.reason,
        "rationale": decision.rationale,
        "parse_errors": "; ".join(decision.parse_errors),
    }
