"""Score agent Decisions against hand-labeled ground truth.

Reports (1) per-field accuracy and (2) how well confidence separates right
answers from wrong ones — AUROC plus a threshold sweep whose semantics match
routing exactly (score >= threshold would auto-file). The sweep's recommended
thresholds are what routing/THRESHOLDS gets set to in step 9.
"""

import csv
import datetime as dt
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from agent.schema import Company, Decision, DocType

SCORED_FIELDS = ("company", "doc_type", "date")
THRESHOLD_GRID = [round(0.50 + 0.05 * i, 2) for i in range(10)]  # 0.50 .. 0.95
TARGET_AUTO_ACCURACY = 0.98

# (confidence score, was the field correct) for one document
Outcome = tuple[float, bool]


@dataclass(frozen=True)
class GroundTruthRow:
    """One hand-labeled document from data/ground_truth.csv."""

    doc_id: str
    company: Company
    doc_type: DocType
    date: dt.date | None


@dataclass(frozen=True)
class SweepPoint:
    """What would happen if this field's routing threshold were ``threshold``:
    ``n_selected`` docs auto-file (``coverage`` as a fraction), with
    ``accuracy`` among them (None if none selected)."""

    threshold: float
    n_selected: int
    coverage: float
    accuracy: float | None


@dataclass(frozen=True)
class FieldEval:
    accuracy: float
    auroc: float | None  # None when all answers are right (or all wrong)
    sweep: list[SweepPoint]
    recommended_threshold: float | None  # smallest grid t hitting the target


@dataclass(frozen=True)
class EvalReport:
    n_scored: int
    missing_decisions: list[str]  # labeled but absent from decisions.jsonl
    missing_labels: list[str]  # decided but absent from ground truth
    fields: dict[str, FieldEval]


def load_ground_truth(csv_path: Path) -> dict[str, GroundTruthRow]:
    """Load the hand-labeled CSV, keyed by doc_id. Fails loudly on any label
    that isn't a verbatim enum value or ISO date — a silently mis-scored
    label is worse than a crash here."""
    rows: dict[str, GroundTruthRow] = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:  # BOM-safe: Excel saves may add one
        reader = csv.DictReader(fh)
        missing = {"doc_id", "company", "doc_type", "date"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{csv_path}: missing columns {sorted(missing)}")
        for line, row in enumerate(reader, start=2):
            doc_id = (row["doc_id"] or "").strip()
            if not doc_id:
                raise ValueError(f"{csv_path} line {line}: empty doc_id")
            if doc_id in rows:
                raise ValueError(f"{csv_path} line {line}: duplicate doc_id {doc_id!r}")
            try:
                # `or ""`: a short row gives None cells — let the enum raise a
                # contextful ValueError instead of a bare AttributeError.
                date_text = (row["date"] or "").strip()
                rows[doc_id] = GroundTruthRow(
                    doc_id=doc_id,
                    company=Company((row["company"] or "").strip()),
                    doc_type=DocType((row["doc_type"] or "").strip()),
                    date=dt.date.fromisoformat(date_text) if date_text else None,
                )
            except ValueError as exc:
                raise ValueError(f"{csv_path} line {line} ({doc_id}): {exc}") from None
    return rows


def load_decisions(jsonl_path: Path) -> dict[str, Decision]:
    """Load the machine record main.py writes (output/decisions.jsonl).
    Fails loudly with line context, same contract as load_ground_truth —
    a hand-merged jsonl deserves the same distrust as a hand-typed CSV."""
    decisions: dict[str, Decision] = {}
    with jsonl_path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            try:
                record = json.loads(line)
                doc_id = record["doc_id"]
                if doc_id in decisions:
                    raise ValueError(f"duplicate doc_id {doc_id!r}")
                decisions[doc_id] = Decision.model_validate(record["decision"])
            except (ValueError, KeyError) as exc:
                raise ValueError(f"{jsonl_path} line {line_no}: {exc}") from None
    return decisions


def evaluate(
    decisions: dict[str, Decision],
    ground_truth: dict[str, GroundTruthRow],
) -> EvalReport:
    """Compare Decisions to ground truth, joined on doc_id."""
    scored_ids = sorted(set(decisions) & set(ground_truth))
    if not scored_ids:
        raise ValueError("no overlapping doc_ids between decisions and ground truth")

    fields = {}
    for field in SCORED_FIELDS:
        # For date, None == None counts CORRECT: a confident "no date" about
        # a genuinely dateless document is the right answer, not a miss.
        outcomes: list[Outcome] = [
            (
                getattr(decisions[doc_id].confidence, field),
                getattr(decisions[doc_id], field) == getattr(ground_truth[doc_id], field),
            )
            for doc_id in scored_ids
        ]
        sweep = _sweep(outcomes)
        fields[field] = FieldEval(
            accuracy=sum(ok for _, ok in outcomes) / len(outcomes),
            auroc=_auroc(outcomes),
            sweep=sweep,
            recommended_threshold=_recommend(sweep),
        )
    return EvalReport(
        n_scored=len(scored_ids),
        missing_decisions=sorted(set(ground_truth) - set(decisions)),
        missing_labels=sorted(set(decisions) - set(ground_truth)),
        fields=fields,
    )


def _auroc(outcomes: list[Outcome]) -> float | None:
    """Rank-based AUROC (Mann-Whitney U, average ranks for ties): the
    probability that a random correct answer carries a higher confidence
    than a random wrong one. Undefined (None) without both kinds."""
    n_pos = sum(ok for _, ok in outcomes)
    n_neg = len(outcomes) - n_pos
    if not n_pos or not n_neg:
        return None
    positions = defaultdict(list)
    for rank, (score, _) in enumerate(sorted(outcomes, key=lambda o: o[0]), start=1):
        positions[score].append(rank)
    avg_rank = {score: sum(ranks) / len(ranks) for score, ranks in positions.items()}
    rank_sum = sum(avg_rank[score] for score, ok in outcomes if ok)
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def _sweep(outcomes: list[Outcome]) -> list[SweepPoint]:
    points = []
    for t in THRESHOLD_GRID:
        selected = [ok for score, ok in outcomes if score >= t]  # >= matches routing
        points.append(
            SweepPoint(
                threshold=t,
                n_selected=len(selected),
                coverage=len(selected) / len(outcomes),
                accuracy=sum(selected) / len(selected) if selected else None,
            )
        )
    return points


def _recommend(sweep: list[SweepPoint]) -> float | None:
    for point in sweep:
        if point.accuracy is not None and point.accuracy >= TARGET_AUTO_ACCURACY:
            return point.threshold
    return None


def format_report(report: EvalReport) -> str:
    lines = [f"scored {report.n_scored} documents (target auto-accuracy {TARGET_AUTO_ACCURACY:.0%})"]
    for field, fe in report.fields.items():
        auroc = f"{fe.auroc:.3f}" if fe.auroc is not None else "n/a (no mix of right/wrong)"
        lines += [f"\n{field}: accuracy {fe.accuracy:.1%}, AUROC {auroc}",
                  "  threshold  auto-filed  auto-accuracy"]
        for p in fe.sweep:
            selected = f"{p.n_selected}/{report.n_scored} ({p.coverage:.0%})"
            accuracy = f"{p.accuracy:.1%}" if p.accuracy is not None else "n/a"
            lines.append(f"  {p.threshold:>9.2f}  {selected:>10}  {accuracy:>13}")
        recommended = (
            f"{fe.recommended_threshold:.2f}"
            if fe.recommended_threshold is not None
            else "none in grid reaches the target"
        )
        lines.append(f"  recommended threshold: {recommended}")
    if report.missing_decisions:
        lines.append(f"\nlabeled but not decided ({len(report.missing_decisions)}): "
                     + ", ".join(report.missing_decisions[:5]))
    if report.missing_labels:
        lines.append(f"decided but not labeled ({len(report.missing_labels)}): "
                     + ", ".join(report.missing_labels[:5]))
    return "\n".join(lines)
