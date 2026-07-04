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
    """One hand-labeled document from data/ground_truth.csv
    (columns doc_id,true_company,true_doc_type,true_date[,difficulty,...])."""

    doc_id: str
    company: Company
    doc_type: DocType
    date: dt.date | None
    difficulty: str | None = None  # optional labeler tag, e.g. clean / hard


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
    by_difficulty: dict[str, tuple[int, int]] | None  # (correct, total) per difficulty tag


@dataclass(frozen=True)
class EvalReport:
    n_scored: int
    n_with_agreement: int  # scored docs that carry a sampling-agreement signal
    missing_decisions: list[str]  # labeled but absent from decisions.jsonl
    missing_labels: list[str]  # decided but absent from ground truth
    fields: dict[str, FieldEval]  # scored on self-reported confidence
    agreement_fields: dict[str, FieldEval] | None  # scored on sampling agreement


def load_ground_truth(csv_path: Path) -> dict[str, GroundTruthRow]:
    """Load the hand-labeled CSV, keyed by doc_id. Fails loudly on any label
    that isn't a verbatim enum value or ISO date — a silently mis-scored
    label is worse than a crash here.

    Required columns: doc_id, true_company, true_doc_type, true_date.
    Optional: difficulty (kept for the report). Other columns are ignored.
    """
    rows: dict[str, GroundTruthRow] = {}
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:  # BOM-safe: Excel saves may add one
        reader = csv.DictReader(fh)
        required = {"doc_id", "true_company", "true_doc_type", "true_date"}
        missing = required - set(reader.fieldnames or [])
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
                date_text = (row["true_date"] or "").strip()
                rows[doc_id] = GroundTruthRow(
                    doc_id=doc_id,
                    company=Company((row["true_company"] or "").strip()),
                    doc_type=DocType((row["true_doc_type"] or "").strip()),
                    date=dt.date.fromisoformat(date_text) if date_text else None,
                    difficulty=(row.get("difficulty") or "").strip() or None,
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
    """Compare Decisions to ground truth.

    Joined on a normalized doc_id: case-folded (Windows filenames are
    case-insensitive) with any trailing ".pdf" stripped — the pipeline's
    doc_id is the filename ("doc_01.pdf") while labelers may write it
    without the extension ("doc_01"). Only ".pdf" is stripped; dotted
    names like "v1.2.report" survive intact.
    """
    decisions_by_stem = _by_join_key(decisions, "decisions")
    truth_by_stem = _by_join_key(ground_truth, "ground truth")
    scored_stems = sorted(set(decisions_by_stem) & set(truth_by_stem))
    if not scored_stems:
        raise ValueError("no overlapping doc_ids between decisions and ground truth")

    pairs = [(decisions_by_stem[s][1], truth_by_stem[s][1]) for s in scored_stems]
    with_agreement = [(d, t) for d, t in pairs if d.agreement is not None]
    return EvalReport(
        n_scored=len(scored_stems),
        n_with_agreement=len(with_agreement),
        missing_decisions=sorted(
            doc_id for stem, (doc_id, _) in truth_by_stem.items() if stem not in decisions_by_stem
        ),
        missing_labels=sorted(
            doc_id for stem, (doc_id, _) in decisions_by_stem.items() if stem not in truth_by_stem
        ),
        fields=_field_evals(pairs, lambda d: d.confidence),
        agreement_fields=(
            _field_evals(with_agreement, lambda d: d.agreement) if with_agreement else None
        ),
    )


def _field_evals(pairs: list, scores_of) -> dict[str, FieldEval]:
    """Score every field over (decision, truth) pairs, reading the per-field
    score from ``scores_of(decision)`` — self-reported confidence or sampling
    agreement; correctness is identical for both."""
    fields = {}
    for field in SCORED_FIELDS:
        # For date, None == None counts CORRECT: a confident "no date" about
        # a genuinely dateless document is the right answer, not a miss.
        outcomes: list[Outcome] = []
        difficulty_counts: dict[str, list[int]] = {}
        for decision, truth in pairs:
            ok = getattr(decision, field) == getattr(truth, field)
            outcomes.append((getattr(scores_of(decision), field), ok))
            if truth.difficulty:
                correct_total = difficulty_counts.setdefault(truth.difficulty, [0, 0])
                correct_total[0] += ok
                correct_total[1] += 1
        sweep = _sweep(outcomes)
        fields[field] = FieldEval(
            accuracy=sum(ok for _, ok in outcomes) / len(outcomes),
            auroc=_auroc(outcomes),
            sweep=sweep,
            recommended_threshold=_recommend(sweep),
            by_difficulty=(
                {tag: (c, t) for tag, (c, t) in sorted(difficulty_counts.items())}
                if difficulty_counts
                else None
            ),
        )
    return fields


def _by_join_key(mapping: dict, source: str) -> dict:
    """Key by the normalized doc_id (case-folded, trailing '.pdf' stripped),
    preserving the original id; collisions are an error (two labels or
    decisions would silently score as one)."""
    keyed: dict[str, tuple[str, object]] = {}
    for doc_id, value in mapping.items():
        key = doc_id.lower().removesuffix(".pdf")
        if key in keyed:
            raise ValueError(
                f"{source}: doc_ids {keyed[key][0]!r} and {doc_id!r} collide on join key {key!r}"
            )
        keyed[key] = (doc_id, value)
    return keyed


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
    lines.append("\n=== signal: self-reported confidence ===")
    lines += _signal_block(report.fields, report.n_scored)
    if report.agreement_fields:
        lines.append(
            f"\n=== signal: sampling agreement (on {report.n_with_agreement} docs) ==="
        )
        lines += _signal_block(report.agreement_fields, report.n_with_agreement)
    if report.missing_decisions:
        lines.append(f"\nlabeled but not decided ({len(report.missing_decisions)}): "
                     + ", ".join(report.missing_decisions[:5]))
    if report.missing_labels:
        lines.append(f"decided but not labeled ({len(report.missing_labels)}): "
                     + ", ".join(report.missing_labels[:5]))
    return "\n".join(lines)


def _signal_block(fields: dict[str, FieldEval], n_total: int) -> list[str]:
    lines = []
    for field, fe in fields.items():
        auroc = f"{fe.auroc:.3f}" if fe.auroc is not None else "n/a (no mix of right/wrong)"
        difficulty = (
            " (" + ", ".join(f"{tag} {c}/{t} ({c / t:.0%})" for tag, (c, t) in fe.by_difficulty.items()) + ")"
            if fe.by_difficulty
            else ""
        )
        lines += [f"\n{field}: accuracy {fe.accuracy:.1%}{difficulty}, AUROC {auroc}",
                  "  threshold  auto-filed  auto-accuracy"]
        for p in fe.sweep:
            selected = f"{p.n_selected}/{n_total} ({p.coverage:.0%})"
            accuracy = f"{p.accuracy:.1%}" if p.accuracy is not None else "n/a"
            lines.append(f"  {p.threshold:>9.2f}  {selected:>10}  {accuracy:>13}")
        recommended = (
            f"{fe.recommended_threshold:.2f}"
            if fe.recommended_threshold is not None
            else "none in grid reaches the target"
        )
        lines.append(f"  recommended threshold: {recommended}")
    return lines
