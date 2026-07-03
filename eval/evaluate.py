"""Score agent Decisions against hand-labeled ground truth.

Reports (1) per-field accuracy and (2) how well confidence separates right
answers from wrong ones — the latter is what routing/ thresholds are set from.
"""

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

from agent.schema import Company, Decision, DocType

SCORED_FIELDS = ("company", "doc_type", "date")


@dataclass(frozen=True)
class GroundTruthRow:
    """One hand-labeled document from data/ground_truth.csv."""

    doc_id: str
    company: Company
    doc_type: DocType
    date: dt.date | None


@dataclass(frozen=True)
class EvalReport:
    """Results of one evaluation run.

    field_accuracy:         fraction correct per field, keyed by SCORED_FIELDS.
    confidence_separation:  per-field metric of how well confidence
                            distinguishes correct from incorrect answers.
                            TODO: pick the metric (AUROC vs mean-confidence
                            gap between right and wrong answers).
    n_documents:            how many docs were scored.
    """

    field_accuracy: dict[str, float]
    confidence_separation: dict[str, float]
    n_documents: int


def load_ground_truth(csv_path: Path) -> dict[str, GroundTruthRow]:
    """Load the hand-labeled CSV, keyed by doc_id.

    Expected columns: doc_id, company, doc_type, date
    (enum values verbatim; date ISO 8601 or empty for "no date").

    TODO: implement after design review.
        - fail loudly on labels that aren't valid enum values
    """
    raise NotImplementedError("Skeleton only — pending design review")


def evaluate(
    decisions: dict[str, Decision],
    ground_truth: dict[str, GroundTruthRow],
) -> EvalReport:
    """Compare Decisions to ground truth (joined on doc_id).

    TODO: implement after design review.
        - per-field accuracy over SCORED_FIELDS
        - confidence separation per field (metric TBD, see EvalReport)
        - decide handling of doc_ids present in one input but not the other
    """
    raise NotImplementedError("Skeleton only — pending design review")
