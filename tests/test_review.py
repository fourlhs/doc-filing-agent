"""Tests for review/report.py — CSV writing, Greek encoding, null handling."""

import csv
import datetime as dt

from agent.parsing import parse_decision
from agent.schema import Company, Decision, DocType, FieldConfidence
from review.report import ENCODING, REVIEW_CSV_COLUMNS, ReviewRow, write_review_csv
from routing.router import route


def clean_row() -> ReviewRow:
    decision = Decision(
        company=Company.HELECTOR,
        doc_type=DocType.INVOICE,
        date=dt.date(2024, 3, 15),
        summary="Τιμολόγιο της Helector προς τον Δήμο Αθηναίων.",
        proposed_filename="2024-03-15_helector_invoice",
        proposed_folder="Helector/invoice/",
        confidence=FieldConfidence(company=0.95, doc_type=0.9, date=0.85),
        rationale="Λογότυπος και ΑΦΜ της Helector.",
    )
    return ReviewRow("a.pdf", "a.pdf", decision, route(decision))


def repaired_row() -> ReviewRow:
    decision = parse_decision({"company": "ΑΚΤΩΡ ΑΤΕ", "date": "15/03/2024"})
    return ReviewRow("b.pdf", "b.pdf", decision, route(decision))


def read_back(path):
    with path.open(encoding=ENCODING, newline="") as fh:
        return list(csv.DictReader(fh))


def test_roundtrip_preserves_greek_and_column_order(tmp_path):
    out = tmp_path / "report.csv"
    write_review_csv([clean_row(), repaired_row()], out)

    with out.open(encoding=ENCODING, newline="") as fh:
        header = next(csv.reader(fh))
    assert header == REVIEW_CSV_COLUMNS

    first, second = read_back(out)
    assert first["summary"] == "Τιμολόγιο της Helector προς τον Δήμο Αθηναίων."
    assert first["company"] == "Helector"
    assert first["date"] == "2024-03-15"
    assert first["confidence_company"] == "0.95"
    assert first["agreement_company"] == ""  # single-sample run: no agreement
    assert first["flag"] == "auto"
    assert first["parse_errors"] == ""

    assert second["company"] == "UNKNOWN"
    assert second["date"] == ""  # malformed date -> null -> empty cell
    assert second["flag"] == "review"
    assert "company is UNKNOWN" in second["reason"]
    assert "ΑΚΤΩΡ ΑΤΕ" in second["parse_errors"]
    assert "; " in second["parse_errors"]  # multiple entries joined


def test_agreement_columns_written_when_present(tmp_path):
    row = clean_row()
    decision = row.decision.model_copy(
        update={"agreement": FieldConfidence(company=0.8, doc_type=1.0, date=0.6)}
    )
    out = tmp_path / "report.csv"
    write_review_csv([ReviewRow(row.doc_id, row.source_name, decision, row.routing)], out)
    (read,) = read_back(out)
    assert read["agreement_company"] == "0.80"
    assert read["agreement_doc_type"] == "1.00"
    assert read["agreement_date"] == "0.60"


def test_bom_present_for_excel(tmp_path):
    out = tmp_path / "report.csv"
    write_review_csv([clean_row()], out)
    assert out.read_bytes()[:3] == b"\xef\xbb\xbf"


def test_every_row_matches_the_declared_columns(tmp_path):
    out = tmp_path / "report.csv"
    write_review_csv([clean_row(), repaired_row()], out)
    with out.open(encoding=ENCODING, newline="") as fh:
        widths = {len(r) for r in csv.reader(fh)}
    assert widths == {len(REVIEW_CSV_COLUMNS)}


def test_hostile_llm_strings_roundtrip_intact(tmp_path):
    # LLM-authored cells can contain the delimiter, quotes, newlines, and
    # the parse_errors join sequence — csv quoting must preserve them all.
    hostile = 'a,"b"\r\nc; d'
    decision = parse_decision(
        {
            "company": "Helector",
            "doc_type": "invoice",
            "date": "2024-03-15",
            "summary": hostile,
            "proposed_filename": "x",
            "proposed_folder": "y/",
            "confidence": {"company": 0.9, "doc_type": 0.9, "date": 0.9},
            "rationale": "π;λ",
        }
    )
    out = tmp_path / "report.csv"
    write_review_csv([ReviewRow("h.pdf", "h.pdf", decision, route(decision))], out)
    (read,) = read_back(out)
    assert read["summary"] == hostile
    assert read["rationale"] == "π;λ"
