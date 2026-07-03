"""Prompts for the classification call. Kept separate so prompt iteration
never touches classifier logic."""

# TODO: write after design review. Must instruct the model to:
#   - identify company (from the fixed Company list, UNKNOWN if unsure),
#     doc_type, and the document's own date
#   - write the one-sentence summary in Greek
#   - derive proposed_filename and proposed_folder from the fields
#   - report honest per-field confidence in [0, 1] — calibration matters
#     more than optimism, low confidence routes to a human (that is fine)
#   - return JSON matching agent.schema.Decision exactly
SYSTEM_PROMPT: str = ""
