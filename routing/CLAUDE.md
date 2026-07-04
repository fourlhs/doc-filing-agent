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
- Thresholds: company 0.90 (calibrated from the 2026-07-04 baseline eval,
  n=22 — a confidently-wrong 0.85 mapping auto-filed at 0.80); doc_type/date
  still provisional 0.80. Step 9 recalibrates from `eval/`, which shows where
  each signal actually separates right from wrong answers. Change with data
  only.
- Imports `agent.schema` only.
