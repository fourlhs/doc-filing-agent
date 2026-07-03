"""Repair layer for LLM output: total parsing, never raises.

The LLM is asked for JSON matching ``Decision``, but its output is untrusted.
``parse_decision`` turns *anything* into a valid ``Decision``: each field that
fails to parse falls back to a safe value with its confidence forced to 0,
which routing/ then sends to human review. Every repair is recorded in
``Decision.parse_errors`` so the reviewer can see what the LLM originally said.

Downstream modules never see an exception and never see an invalid Decision —
strictness stays in the schema, tolerance lives only here, at the LLM boundary.

Scope note: proposed_filename / proposed_folder are format-checked only
(non-empty, valid unicode). Their *content* is untrusted for filesystem use —
main.py must sanitize (traversal, Windows-invalid characters) before building
any real path from them.
"""

import datetime as dt
import json
from enum import Enum
from typing import Any, TypeVar

from agent.schema import Company, Decision, DocType, FieldConfidence

MISSING_TEXT = "[missing]"

E = TypeVar("E", bound=Enum)


def parse_decision(raw: str | dict[str, Any]) -> Decision:
    """Parse raw LLM output into a valid Decision. Total: never raises.

    Accepts a JSON string or an already-decoded dict. Unknown keys are
    ignored. Per-field failures degrade (confidence forced to 0, entry in
    parse_errors); an entirely unusable payload degrades to a full-fallback
    Decision with all confidences 0 — guaranteed human review either way.
    """
    errors: list[str] = []
    payload = _coerce_payload(raw, errors)

    company, company_failed = _parse_enum(
        payload.get("company"), Company, Company.UNKNOWN, "company", errors
    )
    doc_type, doc_type_failed = _parse_enum(
        payload.get("doc_type"), DocType, DocType.OTHER, "doc_type", errors
    )
    date, date_failed = _parse_date(payload.get("date"), errors)

    raw_conf = payload.get("confidence")
    if raw_conf is not None and not isinstance(raw_conf, dict):
        errors.append(
            f"confidence {raw_conf!r} is not an object -> scores treated as missing"
        )
    if not isinstance(raw_conf, dict):
        raw_conf = {}
    # A repaired field's confidence is 0 by definition — the LLM's reported
    # score referred to a value we discarded.
    confidence = FieldConfidence(
        company=0.0
        if company_failed
        else _parse_score(raw_conf.get("company"), "confidence.company", errors),
        doc_type=0.0
        if doc_type_failed
        else _parse_score(raw_conf.get("doc_type"), "confidence.doc_type", errors),
        date=0.0
        if date_failed
        else _parse_score(raw_conf.get("date"), "confidence.date", errors),
    )

    summary = _parse_str(payload.get("summary"), "summary", MISSING_TEXT, errors)
    rationale = _parse_str(payload.get("rationale"), "rationale", MISSING_TEXT, errors)

    proposed_filename = _parse_str(
        payload.get("proposed_filename"),
        "proposed_filename",
        _derive_filename(company, doc_type, date),
        errors,
    )
    proposed_folder = _parse_str(
        payload.get("proposed_folder"),
        "proposed_folder",
        _derive_folder(company, doc_type),
        errors,
    )

    return Decision(
        company=company,
        doc_type=doc_type,
        date=date,
        summary=summary,
        proposed_filename=proposed_filename,
        proposed_folder=proposed_folder,
        confidence=confidence,
        rationale=rationale,
        parse_errors=errors,
    )


def fallback_decision(note: str) -> Decision:
    """Full-fallback Decision (UNKNOWN / OTHER / no date, all confidences 0)
    whose parse_errors carries only ``note``.

    For failures where there is nothing to parse at all: empty document
    content, a response without a tool call, or pipeline errors caught in
    main.py. Confidence 0 guarantees human review.
    """
    return parse_decision({}).model_copy(update={"parse_errors": [note]})


def _coerce_payload(raw: str | dict[str, Any], errors: list[str]) -> dict[str, Any]:
    """Get a dict out of the raw response, or {} (-> full fallback)."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append(
                f"payload is not valid JSON ({exc.msg} at pos {exc.pos}) -> full fallback"
            )
            return {}
        except RecursionError:
            errors.append("payload JSON nested too deeply -> full fallback")
            return {}
        if isinstance(parsed, dict):
            return parsed
        errors.append(
            f"payload JSON is {type(parsed).__name__}, not an object -> full fallback"
        )
        return {}
    errors.append(f"payload is {type(raw).__name__}, not JSON or dict -> full fallback")
    return {}


def _parse_enum(
    value: Any, enum_cls: type[E], fallback: E, field: str, errors: list[str]
) -> tuple[E, bool]:
    """Match against enum values exactly (after strip). Returns (value, failed)."""
    if isinstance(value, str):
        try:
            return enum_cls(value.strip()), False
        except ValueError:
            pass
    errors.append(
        f"{field} {value!r} is not a valid {enum_cls.__name__} "
        f"-> {fallback.value}, confidence forced to 0"
    )
    return fallback, True


def _parse_date(value: Any, errors: list[str]) -> tuple[dt.date | None, bool]:
    """Parse an ISO 8601 date. Returns (date, failed).

    A genuine null is NOT a failure — it means "the LLM confidently found no
    date on the document" and keeps its reported confidence. Only a non-null
    value that can't be parsed forces confidence to 0.
    """
    if value is None:
        return None, False
    if isinstance(value, str):
        text = value.strip()
        try:
            return dt.date.fromisoformat(text), False
        except ValueError:
            pass
        try:
            return dt.datetime.fromisoformat(text).date(), False
        except ValueError:
            pass
    errors.append(f"date {value!r} is not ISO 8601 -> null, confidence forced to 0")
    return None, True


def _parse_score(value: Any, field: str, errors: list[str]) -> float:
    """A confidence score must be a number in [0, 1].

    Out-of-range values are zeroed, NOT clamped: a score of 1.2 means the
    model misread the scale, and we fail toward review, never toward
    auto-filing. bool is rejected (True is not a confidence).
    """
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and 0.0 <= value <= 1.0
    ):
        return float(value)
    errors.append(f"{field} {value!r} is not a number in [0, 1] -> 0")
    return 0.0


def _parse_str(value: Any, field: str, fallback: str, errors: list[str]) -> str:
    """Non-empty string in (repaired to valid UTF-8), else the fallback.

    json.loads accepts lone-surrogate escapes (\\ud800) that would make the
    Decision unserializable downstream — those are replaced here. For the
    proposed filename/folder the fallback is derived from the parsed fields,
    so an auto-filed document can never have an empty name.
    """
    if isinstance(value, str) and value.strip():
        text = value.strip()
        clean = text.encode("utf-8", "replace").decode("utf-8")
        if clean != text:
            errors.append(f"{field} contained invalid unicode -> repaired")
        return clean
    errors.append(f"{field} missing or empty -> {fallback!r}")
    return fallback


def _derive_filename(company: Company, doc_type: DocType, date: dt.date | None) -> str:
    """Deterministic filename from the parsed fields, e.g.
    '2024-03-15_helector_invoice'. No extension — the agent never sees the
    source file; main.py appends the original extension when moving."""
    date_part = date.isoformat() if date is not None else "undated"
    company_part = company.value.lower().replace(" ", "-")
    return f"{date_part}_{company_part}_{doc_type.value}"


def _derive_folder(company: Company, doc_type: DocType) -> str:
    """Deterministic filing path from the parsed fields, e.g. 'Helector/invoice/'."""
    return f"{company.value}/{doc_type.value}/"
