"""The shared contract of the entire pipeline: what the agent consumes
(DocumentContent) and what it returns (Decision).

Every other module depends on this file and nothing else in agent/. It must
stay pydantic/stdlib-only — importing the contract must never drag in the
LLM SDK. Change it deliberately: the whole pipeline feels it.
"""

import datetime as dt
from enum import Enum

from pydantic import BaseModel, Field


class DocumentContent(BaseModel):
    """What ingestion hands the agent for one document.

    text-only in v1 (PDF text layer). ``pages`` (rendered page images, PNG
    bytes) exists so an OCR/vision extractor can be added later without
    changing the agent's signature.
    """

    text: str | None = None
    pages: list[bytes] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """True when there is nothing usable to classify."""
        return not (self.text and self.text.strip()) and not self.pages


class Company(str, Enum):
    """The group entity the document belongs to. UNKNOWN forces human review."""

    AKTOR_CONSTRUCTION = "Aktor Construction"
    AKTOR_CONCESSIONS = "Aktor Concessions"
    AKTOR_AI = "Aktor AI"
    HELECTOR = "Helector"
    AKTOR_FACILITY_MANAGEMENT = "Aktor Facility Management"
    AKTOR_REAL_ESTATE = "Aktor Real Estate"
    AKTOR_GROUP = "Aktor Group"
    UNKNOWN = "UNKNOWN"


class DocType(str, Enum):
    """Kind of business document."""

    CONTRACT = "contract"
    INVOICE = "invoice"
    COURT_FILING = "court_filing"
    CORRESPONDENCE = "correspondence"
    PERMIT = "permit"
    TECHNICAL_REPORT = "technical_report"
    FINANCIAL_STATEMENT = "financial_statement"
    HR_DOCUMENT = "hr_document"
    OTHER = "OTHER"


class FieldConfidence(BaseModel):
    """Per-field confidence, 0.0 (guess) to 1.0 (certain).

    Per-field — not one overall score — so routing can send a document to
    human review when any single field is shaky.
    """

    company: float = Field(ge=0.0, le=1.0)
    doc_type: float = Field(ge=0.0, le=1.0)
    date: float = Field(ge=0.0, le=1.0)


class Decision(BaseModel):
    """The agent's structured answer for one document."""

    company: Company
    doc_type: DocType
    date: dt.date | None = Field(
        description="The document's own date (ISO 8601), or null if none found."
    )
    summary: str = Field(
        description="One sentence, in Greek, saying what the document is."
    )
    proposed_filename: str = Field(
        description="Derived from company/doc_type/date, lowercase, no "
        "extension, e.g. '2024-03-15_helector_invoice'."
    )
    proposed_folder: str = Field(
        description="Filing path '<Company>/<doc_type>/', e.g. "
        "'Helector/invoice/'."
    )
    confidence: FieldConfidence
    rationale: str = Field(
        description="One sentence on why company/doc_type/date were chosen."
    )
    parse_errors: list[str] = Field(
        default_factory=list,
        description="One entry per field the parser had to repair, e.g. "
        "\"company 'ΑΚΤΩΡ ΑΤΕ' is not a valid Company -> UNKNOWN\". "
        "Empty means the LLM output parsed cleanly. Populated only by "
        "agent.parsing — the LLM is not asked for this field.",
    )
    agreement: FieldConfidence | None = Field(
        default=None,
        description="Sampling agreement: fraction of k samples that reproduce "
        "this decision's value, per field — an empirical P(same answer again). "
        "Populated only by the classifier on multi-sample runs (--samples k>1); "
        "the LLM is not asked for this field. Measurement only: routing reads "
        "confidence, not this.",
    )
