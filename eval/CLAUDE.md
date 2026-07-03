# eval/

**Single responsibility:** measure the agent against hand-labeled ground truth.
Two questions: (1) per-field accuracy — how often are company / doc_type / date
right? (2) calibration — does confidence actually separate right answers from
wrong ones?

- Input: the agent's `Decision`s plus `data/ground_truth.csv` with columns
  `doc_id,company,doc_type,date` (values must match the schema enums verbatim;
  date ISO 8601 or empty for none).
- Output: an `EvalReport` — per-field accuracy and a per-field confidence
  separation metric (exact metric is TODO: AUROC vs mean-confidence gap).
- The calibration result is what sets the thresholds in `routing/` — eval
  informs routing, it never imports it.
- Imports `agent.schema` only. Never imports `ingestion/`.
