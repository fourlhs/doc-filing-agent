"""Tests for eval/evaluate.py — hand-computable accuracy, AUROC, and sweep."""

import datetime as dt
from pathlib import Path

import pytest

from agent.parsing import parse_decision
from eval.evaluate import (
    GroundTruthRow,
    _auroc,
    evaluate,
    load_ground_truth,
)
from agent.schema import Company, DocType


def decision(company="Helector", date="2024-03-15", conf_company=0.9):
    return parse_decision(
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


def truth(doc_id, company=Company.HELECTOR, date=dt.date(2024, 3, 15)):
    return GroundTruthRow(doc_id, company, DocType.INVOICE, date)


# --- load_ground_truth -------------------------------------------------------


def write_csv(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "gt.csv"
    path.write_text("doc_id,company,doc_type,date\n" + body, encoding="utf-8")
    return path


def test_load_ground_truth_parses_labels_and_empty_date(tmp_path):
    path = write_csv(tmp_path, "a.pdf,Helector,invoice,2024-03-15\nb.pdf,Aktor AI,contract,\n")
    rows = load_ground_truth(path)
    assert rows["a.pdf"].company == Company.HELECTOR
    assert rows["a.pdf"].date == dt.date(2024, 3, 15)
    assert rows["b.pdf"].company == Company.AKTOR_AI
    assert rows["b.pdf"].date is None


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
    path.write_text("doc_id,company\na.pdf,Helector\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        load_ground_truth(path)


def test_load_ground_truth_accepts_excel_bom(tmp_path):
    path = tmp_path / "gt.csv"
    path.write_text("doc_id,company,doc_type,date\na.pdf,Helector,invoice,\n", encoding="utf-8-sig")
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


def test_evaluate_requires_overlap():
    with pytest.raises(ValueError, match="no overlapping doc_ids"):
        evaluate({"a.pdf": decision()}, {"b.pdf": truth("b.pdf")})
