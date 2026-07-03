# routing/

**Single responsibility:** decide, from a `Decision`'s per-field confidences,
whether a document files automatically (`auto`) or goes to a human (`review`)
— and say why.

- Pure function: `Decision` in -> `RoutingResult(destination, reason)` out.
  Deterministic threshold rules, NO reasoning (that lives in `agent/`) and
  NO filesystem access (moving files is `main.py`'s job).
- Rules: `review` if `company == UNKNOWN` or any field's confidence is below
  its threshold; otherwise `auto`. The reason must name the trigger.
- Thresholds are TODO — set them after `eval/` shows where confidence
  actually separates right from wrong answers.
- Imports `agent.schema` only.
