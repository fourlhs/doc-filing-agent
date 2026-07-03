# routing/

**Single responsibility:** decide, from a `Decision`'s per-field confidences,
whether a document files automatically (`auto`) or goes to a human (`review`)
— and say why.

- Pure function: `Decision` in -> `RoutingResult(destination, reason)` out.
  Deterministic threshold rules, NO reasoning (that lives in `agent/`) and
  NO filesystem access (copying files is `main.py`'s job).
- Rules: `review` if `company == UNKNOWN` or any field's confidence is
  strictly below its threshold (equality passes); otherwise `auto`. The
  reason names every trigger with its numbers.
- Thresholds are provisional (0.80) — step 9 recalibrates them from `eval/`,
  which shows where confidence actually separates right from wrong answers.
- Imports `agent.schema` only.
