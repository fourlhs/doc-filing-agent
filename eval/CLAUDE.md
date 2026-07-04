# eval/

**Single responsibility:** measure the agent against hand-labeled ground truth.
Two questions: (1) per-field accuracy — how often are company / doc_type / date
right? (2) calibration — does confidence actually separate right answers from
wrong ones?

- Input: the agent's `Decision`s plus `data/ground_truth.csv` with columns
  `doc_id,true_company,true_doc_type,true_date` (+ optional `difficulty`,
  extras ignored; enum values verbatim; date ISO 8601 or empty for none).
  Joins case-insensitively on the doc_id with any trailing `.pdf` stripped,
  so labels may omit the extension (dotted names like `v1.2.report` survive). A
  decision of "no date" against an empty date label counts as CORRECT —
  confidently saying a dateless document has no date is the right answer.
- Output: an `EvalReport` — per-field accuracy, per-field AUROC (rank-based,
  no sklearn), and a threshold sweep (0.50–0.95) whose `score >= t` semantics
  match routing exactly, with a recommended threshold per field (smallest t
  reaching the target auto-accuracy).
- The calibration result is what sets the thresholds in `routing/` — eval
  informs routing, it never imports it.
- Imports `agent.schema` only. Never imports `ingestion/`.
