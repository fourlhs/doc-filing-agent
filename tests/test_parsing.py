"""Tests for agent/parsing.py — the never-crash repair layer.

Pure logic: no LLM, no I/O. The invariant under test: parse_decision is
total — any input yields a valid Decision, and every repaired field has
confidence 0 so routing sends the doc to review.
"""

import datetime as dt
import json

import pytest

from agent.parsing import MISSING_TEXT, parse_decision
from agent.schema import Company, DocType


def make_payload(**overrides):
    """A clean, fully valid payload; override single fields to break them."""
    payload = {
        "company": "Helector",
        "doc_type": "invoice",
        "date": "2024-03-15",
        "summary": "Τιμολόγιο της Helector προς τον Δήμο Αθηναίων.",
        "proposed_filename": "2024-03-15_helector_invoice",
        "proposed_folder": "Helector/invoice/",
        "confidence": {"company": 0.95, "doc_type": 0.9, "date": 0.85},
        "rationale": "Ο λογότυπος και το ΑΦΜ ταιριάζουν με τη Helector.",
    }
    payload.update(overrides)
    return payload


# --- clean input -----------------------------------------------------------


def test_clean_payload_parses_exactly():
    decision = parse_decision(make_payload())
    assert decision.company == Company.HELECTOR
    assert decision.doc_type == DocType.INVOICE
    assert decision.date == dt.date(2024, 3, 15)
    assert decision.summary == "Τιμολόγιο της Helector προς τον Δήμο Αθηναίων."
    assert decision.proposed_filename == "2024-03-15_helector_invoice"
    assert decision.proposed_folder == "Helector/invoice/"
    assert decision.confidence.company == 0.95
    assert decision.confidence.doc_type == 0.9
    assert decision.confidence.date == 0.85
    assert decision.parse_errors == []


def test_clean_payload_as_json_string():
    decision = parse_decision(json.dumps(make_payload()))
    assert decision.company == Company.HELECTOR
    assert decision.parse_errors == []


def test_enum_values_tolerate_surrounding_whitespace():
    decision = parse_decision(make_payload(company="  Helector ", doc_type=" invoice"))
    assert decision.company == Company.HELECTOR
    assert decision.doc_type == DocType.INVOICE
    assert decision.parse_errors == []


# --- per-field repair: company / doc_type ----------------------------------


def test_invalid_company_falls_back_to_unknown_with_zero_confidence():
    decision = parse_decision(make_payload(company="ΑΚΤΩΡ ΑΤΕ"))
    assert decision.company == Company.UNKNOWN
    assert decision.confidence.company == 0.0
    assert any("company" in e for e in decision.parse_errors)
    # other fields untouched
    assert decision.doc_type == DocType.INVOICE
    assert decision.confidence.doc_type == 0.9


def test_invalid_doc_type_falls_back_to_other_with_zero_confidence():
    decision = parse_decision(make_payload(doc_type="τιμολόγιο"))
    assert decision.doc_type == DocType.OTHER
    assert decision.confidence.doc_type == 0.0
    assert any("doc_type" in e for e in decision.parse_errors)


def test_field_fallback_overrides_reported_confidence():
    # LLM is 0.99 confident in a company that doesn't exist — the score
    # refers to a value we discarded, so it must be forced to 0.
    payload = make_payload(
        company="Aktor Shipping",
        confidence={"company": 0.99, "doc_type": 0.9, "date": 0.85},
    )
    decision = parse_decision(payload)
    assert decision.company == Company.UNKNOWN
    assert decision.confidence.company == 0.0


# --- per-field repair: date --------------------------------------------------


def test_malformed_date_becomes_null_with_zero_confidence():
    decision = parse_decision(make_payload(date="15/03/2024"))
    assert decision.date is None
    assert decision.confidence.date == 0.0
    assert any("date" in e for e in decision.parse_errors)


def test_genuine_null_date_keeps_reported_confidence():
    # "No date on this document" is a legitimate, confident answer.
    payload = make_payload(
        date=None, confidence={"company": 0.95, "doc_type": 0.9, "date": 0.9}
    )
    decision = parse_decision(payload)
    assert decision.date is None
    assert decision.confidence.date == 0.9
    assert decision.parse_errors == []


def test_iso_datetime_string_is_accepted_as_date():
    decision = parse_decision(make_payload(date="2024-03-15T10:30:00"))
    assert decision.date == dt.date(2024, 3, 15)
    assert decision.confidence.date == 0.85
    assert decision.parse_errors == []


# --- per-field repair: confidence scores ------------------------------------


@pytest.mark.parametrize(
    "bad_score",
    ["high", 1.2, -0.1, None, True, [0.9]],
    ids=["string", "above-range", "below-range", "missing", "bool", "list"],
)
def test_bad_confidence_score_becomes_zero(bad_score):
    payload = make_payload(
        confidence={"company": bad_score, "doc_type": 0.9, "date": 0.85}
    )
    decision = parse_decision(payload)
    assert decision.confidence.company == 0.0
    assert decision.confidence.doc_type == 0.9  # others untouched
    assert any("confidence.company" in e for e in decision.parse_errors)


def test_missing_confidence_object_zeroes_all_scores():
    payload = make_payload()
    del payload["confidence"]
    decision = parse_decision(payload)
    assert decision.confidence.company == 0.0
    assert decision.confidence.doc_type == 0.0
    assert decision.confidence.date == 0.0


def test_confidence_not_an_object_zeroes_all_scores():
    decision = parse_decision(make_payload(confidence="very confident"))
    assert decision.confidence.company == 0.0
    assert decision.confidence.doc_type == 0.0
    assert decision.confidence.date == 0.0
    assert any("confidence" in e for e in decision.parse_errors)


# --- per-field repair: text and derived names --------------------------------


def test_missing_summary_gets_placeholder():
    payload = make_payload()
    del payload["summary"]
    decision = parse_decision(payload)
    assert decision.summary == MISSING_TEXT
    # summary is not a scored field: routing-relevant confidences untouched
    assert decision.confidence.company == 0.95


def test_missing_filename_and_folder_are_derived_deterministically():
    decision = parse_decision(make_payload(proposed_filename="", proposed_folder=None))
    assert decision.proposed_filename == "2024-03-15_helector_invoice"
    assert decision.proposed_folder == "Helector/invoice/"
    assert len(decision.parse_errors) == 2


def test_derived_filename_when_undated():
    payload = make_payload(
        date=None,
        proposed_filename="",
        confidence={"company": 0.95, "doc_type": 0.9, "date": 0.9},
    )
    decision = parse_decision(payload)
    assert decision.proposed_filename == "undated_helector_invoice"


# --- whole-payload failure ----------------------------------------------------


@pytest.mark.parametrize(
    "garbage",
    ["this is not json at all", "[1, 2, 3]", '"just a string"', "{invalid json", ""],
    ids=["prose", "json-array", "json-scalar", "truncated-json", "empty-string"],
)
def test_unusable_payload_degrades_to_full_fallback(garbage):
    decision = parse_decision(garbage)
    assert decision.company == Company.UNKNOWN
    assert decision.doc_type == DocType.OTHER
    assert decision.date is None
    assert decision.confidence.company == 0.0
    assert decision.confidence.doc_type == 0.0
    assert decision.confidence.date == 0.0
    assert decision.parse_errors  # the trail says what happened
    assert decision.proposed_filename  # derived, never empty
    assert decision.proposed_folder


def test_unknown_extra_keys_are_ignored():
    decision = parse_decision(make_payload(extra_field="whatever"))
    assert decision.parse_errors == []


def test_deeply_nested_json_degrades_instead_of_recursion_error():
    decision = parse_decision("[" * 3000 + "]" * 3000)
    assert decision.company == Company.UNKNOWN
    assert decision.confidence.company == 0.0
    assert any("nested too deeply" in e for e in decision.parse_errors)


def test_lone_surrogate_string_is_repaired_and_decision_stays_serializable():
    # json.loads accepts "\ud800" escapes; unrepaired, the Decision would
    # blow up later at serialization time (CSV/JSON), far from this boundary.
    decision = parse_decision(make_payload(summary="\ud800 kakó unicode"))
    decision.model_dump_json()  # must not raise
    assert any("summary" in e and "unicode" in e for e in decision.parse_errors)
