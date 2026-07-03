"""The Decision schema — the shared contract of the entire pipeline.

The agent must return exactly this structure for every document. routing/,
eval/, and review/ all depend on this module and nothing else in agent/.
Change it deliberately: every downstream module feels it.
"""

import datetime as dt
from enum import Enum

from pydantic import BaseModel, Field


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
        description="Derived from company/doc_type/date, e.g. "
        "'2024-03-15_helector_invoice.pdf'."
    )
    proposed_folder: str = Field(
        description="Filing path derived from the fields, e.g. "
        "'Helector/invoices/2024/'."
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
