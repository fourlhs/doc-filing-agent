# review/

**Single responsibility:** write the human-readable CSV report — every
document, its proposed decision, per-field confidences, and its auto/review
flag with the reason.

- One row per document, ALL documents (not just flagged ones): the reviewer
  needs to spot-check auto-filed docs too.
- Pure formatting: takes already-computed objects (doc identity, `Decision`,
  `RoutingResult`) and serializes them. No reasoning, no thresholds, no
  re-deciding anything.
- Imports `agent.schema` and `routing.router` (for the result types) only.
  Never imports `ingestion/`.
