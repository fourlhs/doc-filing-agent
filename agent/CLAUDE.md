# agent/

**Single responsibility:** the reasoning core. Takes extracted text, returns a
structured `Decision` via one LLM call. This is the ONLY module that reasons.

- Pure with respect to the world: text in -> `Decision` out. No file reads, no
  file writes, no knowledge of where documents live. Its only external contact
  is the LLM API.
- `schema.py` is the shared contract of the whole pipeline: `routing/`,
  `eval/`, and `review/` import `Decision` from here and nothing else from
  this module.
- Never imports from `ingestion/`, `routing/`, `review/`, or `eval/`.
- Confidence scores must be per-field (company, doc_type, date) so routing
  can flag a doc when any single field is shaky.
- **Never crashes on malformed LLM output.** Every raw response goes through
  `parsing.parse_decision`, which repairs each invalid field to a safe
  fallback (`UNKNOWN` / `OTHER` / null date) with that field's confidence
  forced to 0, and records the repair in `Decision.parse_errors`. Downstream
  always receives a valid `Decision`; a parse failure surfaces as a
  review-routed document, never an exception. Repair lives here — not in
  the schema, not downstream — because this module owns the LLM boundary.
- `Decision.proposed_filename` / `proposed_folder` are format-checked only;
  their content is UNTRUSTED for filesystem use. Path sanitization
  (traversal, Windows-invalid characters) is main.py's job at the filing
  step — the agent has no filesystem knowledge to sanitize against.
