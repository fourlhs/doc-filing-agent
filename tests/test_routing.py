"""Tests for routing/router.py — the auto-vs-review rule matrix."""

import datetime as dt

import pytest

from agent.parsing import parse_decision
from agent.schema import Company, Decision, DocType, FieldConfidence
from routing.router import THRESHOLDS, Destination, route


def make_decision(company=Company.HELECTOR, confidence: dict | None = None) -> Decision:
    conf = {"company": 0.95, "doc_type": 0.90, "date": 0.85, **(confidence or {})}
    return Decision(
        company=company,
        doc_type=DocType.INVOICE,
        date=dt.date(2024, 3, 15),
        summary="Τιμολόγιο.",
        proposed_filename="2024-03-15_helector_invoice",
        proposed_folder="Helector/invoice/",
        confidence=FieldConfidence(**conf),
        rationale="Λογότυπος.",
    )


def test_all_confident_goes_auto():
    result = route(make_decision())
    assert result.destination == Destination.AUTO
    assert result.reason == "all confidences at or above thresholds"


def test_unknown_company_goes_review_even_with_high_confidence():
    result = route(make_decision(company=Company.UNKNOWN))  # confidences all high
    assert result.destination == Destination.REVIEW
    assert "company is UNKNOWN" in result.reason


@pytest.mark.parametrize("field", ["company", "doc_type", "date"])
def test_single_low_field_goes_review_and_is_named(field):
    result = route(make_decision(confidence={field: 0.42}))
    assert result.destination == Destination.REVIEW
    assert result.reason == f"{field} confidence 0.42 below threshold 0.80"


def test_multiple_triggers_all_listed():
    decision = make_decision(company=Company.UNKNOWN, confidence={"date": 0.10})
    result = route(decision)
    assert result.destination == Destination.REVIEW
    assert result.reason == (
        "company is UNKNOWN; date confidence 0.10 below threshold 0.80"
    )


def test_confidence_exactly_at_threshold_passes():
    at_threshold = {"company": 0.80, "doc_type": 0.80, "date": 0.80}
    result = route(make_decision(confidence=at_threshold))
    assert result.destination == Destination.AUTO


def test_parsing_fallback_decision_always_goes_review():
    result = route(parse_decision("garbage"))
    assert result.destination == Destination.REVIEW
    assert "company is UNKNOWN" in result.reason


def test_thresholds_cover_every_confidence_field():
    # A field added to FieldConfidence but missing here would silently
    # never be checked — the exact failure routing exists to prevent.
    assert set(THRESHOLDS) == set(FieldConfidence.model_fields)
