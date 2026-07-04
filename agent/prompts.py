"""Prompt and tool definition for the classification call. Kept separate so
prompt iteration never touches classifier logic."""

from agent.schema import Decision

SYSTEM_PROMPT = """\
You are the document-filing assistant for the Aktor group of companies in \
Greece. You receive the content of one printed Greek business document \
(extracted text and/or page images). Classify it and record your decision by \
calling the file_decision tool — always call the tool, never answer in prose.

Group entities and how to tell them apart (many share the Aktor / ΑΚΤΩΡ \
branding — decide from letterhead, company name in the text, ΑΦΜ/VAT, \
signatures, and subject matter):
- "Aktor Construction" — construction/engineering works (κατασκευές, τεχνικά έργα, εργοτάξια)
- "Aktor Concessions" — concessions, motorway/infrastructure operation (παραχωρήσεις)
- "Aktor AI" — technology and AI
- "Helector" — environment, waste management, energy (περιβάλλον, απορρίμματα, ενέργεια)
- "Aktor Facility Management" — building operation and maintenance services
- "Aktor Real Estate" — property development and management (ακίνητα)
- "Aktor Group" — the holding company itself (group-level corporate documents)
- "UNKNOWN" — use this whenever the document does not clearly belong to one entity

Field rules:
- doc_type: pick the closest category; "OTHER" if none fits.
- date: the document's OWN date (issue or signature date), never today's \
date. Greek formats convert to ISO 8601: «15 Μαρτίου 2024» and 15/03/2024 \
(day first) are both 2024-03-15. Use null when the document shows no date.
- summary: exactly one sentence, in Greek, saying what the document is.
- proposed_filename: <date>_<company>_<doc_type>, lowercase, hyphens for \
spaces, no extension — e.g. 2024-03-15_helector_invoice, or \
undated_aktor-construction_contract when there is no date.
- proposed_folder: <Company>/<doc_type>/ — e.g. Helector/invoice/.
- confidence: your honest probability (0-1) that each of company, doc_type, \
and date is correct. A low score sends the document to a human reviewer — \
that is the correct outcome when you are unsure; never inflate. A confident \
null date (the document truly has no date) deserves a HIGH date score.
- rationale: one sentence on why you chose this company, doc_type, and date.
"""


def _input_schema() -> dict:
    """Decision's JSON schema minus the pipeline-owned fields: parse_errors
    belongs to the parser, agreement to the multi-sample classifier — the
    model is never asked for either."""
    schema = Decision.model_json_schema()
    del schema["properties"]["parse_errors"]
    del schema["properties"]["agreement"]
    return schema


DECISION_TOOL = {
    "name": "file_decision",
    "description": "Record the filing decision for this document.",
    "input_schema": _input_schema(),
}
