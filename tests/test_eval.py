"""Tests for eval/evaluate.py — hand-computable accuracy, AUROC, and sweep."""

import datetime as dt
from pathlib import Path

import pytest

from agent.parsing import parse_decision
from eval.evaluate import (
    GroundTruthRow,
    _auroc,
    evaluate,
    format_report,
    load_ground_truth,
)
from agent.schema import Company, DocType, FieldConfidence


def decision(company="Helector", date="2024-03-15", conf_company=0.9, agreement=None):
    parsed = parse_decision(
        {
            "company": company,
            "doc_type": "invoice",
            "date": date,
            "summary": "χ",
            "proposed_filename": "f",
            "proposed_folder": "p/",
            "confidence": {"company": conf_company, "doc_type": 0.9, "date": 0.9},
            "rationale": "χ",
        }
    )
    if agreement is not None:
        parsed = parsed.model_copy(
            update={"agreement": FieldConfidence(company=agreement, doc_type=1.0, date=1.0)}
        )
    return parsed


def truth(doc_id, company=Company.HELECTOR, date=dt.date(2024, 3, 15), difficulty=None):
    return GroundTruthRow(doc_id, company, DocType.INVOICE, date, difficulty)


# --- load_ground_truth -------------------------------------------------------


def write_csv(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "gt.csv"
    path.write_text("doc_id,true_company,true_doc_type,true_date\n" + body, encoding="utf-8")
    return path


def test_load_ground_truth_parses_labels_and_empty_date(tmp_path):
    path = write_csv(tmp_path, "a.pdf,Helector,invoice,2024-03-15\nb.pdf,Aktor AI,contract,\n")
    rows = load_ground_truth(path)
    assert rows["a.pdf"].company == Company.HELECTOR
    assert rows["a.pdf"].date == dt.date(2024, 3, 15)
    assert rows["a.pdf"].difficulty is None
    assert rows["b.pdf"].company == Company.AKTOR_AI
    assert rows["b.pdf"].date is None


def test_load_ground_truth_reads_difficulty_and_ignores_extra_columns(tmp_path):
    path = tmp_path / "gt.csv"
    path.write_text(
        "doc_id,true_company,true_doc_type,true_date,difficulty,note\n"
        "doc_01,Helector,invoice,2024-03-15,hard,two dates on page\n",
        encoding="utf-8",
    )
    rows = load_ground_truth(path)
    assert rows["doc_01"].difficulty == "hard"


@pytest.mark.parametrize(
    ("body", "match"),
    [
        ("a.pdf,Helektor,invoice,2024-03-15\n", r"line 2 \(a\.pdf\).*not a valid Company"),
        ("a.pdf,Helector,tim,2024-03-15\n", r"line 2 \(a\.pdf\).*not a valid DocType"),
        ("a.pdf,Helector,invoice,15/03/2024\n", r"line 2 \(a\.pdf\).*isoformat"),
        ("a.pdf,Helector\n", r"line 2 \(a\.pdf\).*not a valid DocType"),  # short row
        ("a.pdf,Helector,invoice,\nb.pdf,Helector,invoice,\na.pdf,Helector,invoice,\n", "duplicate"),
        (",Helector,invoice,\n", "empty doc_id"),
    ],
)
def test_load_ground_truth_fails_loudly_on_bad_labels(tmp_path, body, match):
    with pytest.raises(ValueError, match=match):
        load_ground_truth(write_csv(tmp_path, body))


def test_load_ground_truth_rejects_missing_columns(tmp_path):
    path = tmp_path / "gt.csv"
    path.write_text("doc_id,true_company\na.pdf,Helector\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        load_ground_truth(path)


def test_load_ground_truth_accepts_excel_bom(tmp_path):
    path = tmp_path / "gt.csv"
    path.write_text(
        "doc_id,true_company,true_doc_type,true_date\na.pdf,Helector,invoice,\n",
        encoding="utf-8-sig",
    )
    assert "a.pdf" in load_ground_truth(path)


# --- AUROC -------------------------------------------------------------------


def test_auroc_hand_computed_cases():
    assert _auroc([(0.9, True), (0.8, True), (0.4, False)]) == 1.0  # perfect
    assert _auroc([(0.4, True), (0.9, False)]) == 0.0  # inverted
    assert _auroc([(0.9, True), (0.5, False), (0.6, True), (0.8, False)]) == 0.75
    assert _auroc([(0.8, True), (0.8, False)]) == 0.5  # tie -> chance
    assert _auroc([(0.9, True), (0.8, True)]) is None  # degenerate: all correct


# --- evaluate ----------------------------------------------------------------


def test_evaluate_accuracy_sweep_and_joins():
    decisions = {
        "a.pdf": decision(conf_company=0.95),  # right, confident
        "b.pdf": decision(conf_company=0.90),  # right, confident
        "c.pdf": decision(company="Aktor AI", conf_company=0.60),  # wrong, hesitant
        "d.pdf": decision(conf_company=0.70),  # right, hesitant
        "zz.pdf": decision(),  # not labeled
    }
    ground_truth = {doc: truth(doc) for doc in ("a.pdf", "b.pdf", "c.pdf", "d.pdf")}
    ground_truth["missing.pdf"] = truth("missing.pdf")

    report = evaluate(decisions, ground_truth)

    assert report.n_scored == 4
    assert report.missing_labels == ["zz.pdf"]
    assert report.missing_decisions == ["missing.pdf"]

    company = report.fields["company"]
    assert company.accuracy == 0.75  # 3 of 4
    assert company.auroc == 1.0  # both correct-confident above the wrong one
    at_080 = next(p for p in company.sweep if p.threshold == 0.80)
    assert at_080.n_selected == 2  # a and b
    assert at_080.coverage == 0.5
    assert at_080.accuracy == 1.0  # both right
    assert company.recommended_threshold == 0.65  # first t excluding the 0.60 error

    # date: all four correct at 0.9 -> degenerate AUROC, recommend lowest t
    date = report.fields["date"]
    assert date.accuracy == 1.0
    assert date.auroc is None
    assert date.recommended_threshold == 0.50

    # no decision carries agreement -> no agreement block
    assert report.n_with_agreement == 0
    assert report.agreement_fields is None
    assert "sampling agreement" not in format_report(report)


def test_agreement_signal_scored_separately_from_confidence():
    # Both docs equally self-confident (0.9), but the wrong one is unstable
    # under sampling: confidence can't separate them, agreement can.
    decisions = {
        "a.pdf": decision(agreement=1.0),  # right, stable
        "b.pdf": decision(company="Aktor AI", agreement=0.2),  # wrong, unstable
    }
    ground_truth = {doc: truth(doc) for doc in ("a", "b")}

    report = evaluate(decisions, ground_truth)

    assert report.n_with_agreement == 2
    assert report.fields["company"].auroc == 0.5  # tie: 0.9 vs 0.9
    assert report.agreement_fields["company"].auroc == 1.0  # 1.0 vs 0.2
    rendered = format_report(report)
    assert "=== signal: sampling agreement (on 2 docs) ===" in rendered


def test_evaluate_requires_overlap():
    with pytest.raises(ValueError, match="no overlapping doc_ids"):
        evaluate({"a.pdf": decision()}, {"b.pdf": truth("b.pdf")})


def test_evaluate_joins_extensionless_and_case_insensitive_labels():
    # Labeler writes "Doc_01"; the pipeline's doc_id is "doc_01.pdf".
    report = evaluate({"doc_01.pdf": decision()}, {"Doc_01": truth("Doc_01")})
    assert report.n_scored == 1
    assert report.missing_decisions == []
    assert report.missing_labels == []


def test_evaluate_strips_only_the_pdf_suffix_from_dotted_names():
    report = evaluate({"v1.2.report.pdf": decision()}, {"v1.2.report": truth("v1.2.report")})
    assert report.n_scored == 1


def test_evaluate_missing_lists_carry_original_ids():
    report = evaluate(
        {"a.pdf": decision(), "extra.pdf": decision()},
        {"a": truth("a"), "unprocessed": truth("unprocessed")},
    )
    assert report.missing_decisions == ["unprocessed"]  # as the labeler wrote it
    assert report.missing_labels == ["extra.pdf"]  # as the pipeline wrote it


def test_evaluate_splits_accuracy_by_difficulty_with_counts():
    decisions = {
        "a.pdf": decision(),  # right
        "b.pdf": decision(company="Aktor AI"),  # wrong company
    }
    ground_truth = {
        "a": truth("a", difficulty="clean"),
        "b": truth("b", difficulty="hard"),
    }
    report = evaluate(decisions, ground_truth)
    assert report.fields["company"].by_difficulty == {"clean": (1, 1), "hard": (0, 1)}
    rendered = format_report(report)
    assert "clean 1/1 (100%)" in rendered
    assert "hard 0/1 (0%)" in rendered


@pytest.mark.parametrize(
    ("decisions_ids", "truth_ids", "source"),
    [(("a.pdf", "A"), ("b",), "decisions"), (("b.pdf",), ("a", "A.pdf"), "ground truth")],
)
def test_evaluate_rejects_join_key_collisions_on_either_side(decisions_ids, truth_ids, source):
    decisions = {doc_id: decision() for doc_id in decisions_ids}
    ground_truth = {doc_id: truth(doc_id) for doc_id in truth_ids}
    with pytest.raises(ValueError, match=f"{source}: .*collide on join key"):
        evaluate(decisions, ground_truth)
