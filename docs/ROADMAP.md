# Roadmap: skeleton → working v1

Approved 2026-07-03. Update checkboxes as steps complete; one git commit per step.

## Decisions locked

| Decision | Choice |
|---|---|
| Extraction | pypdf text layer v1; extractor swappable; agent contract supports text *or page images* from day one (OCR/vision addable without contract change) |
| Model | claude-sonnet-5 (Haiku comparison via eval later) |
| Filing | **Copy** (originals stay in `input/`); AUTO mirrors `proposed_folder` under `output/auto/`; REVIEW copied to `output/review/` under original name |
| Scale | 10–50 docs/run, sequential, per-doc error isolation |
| Thresholds | Provisional 0.80 all fields; calibrated in step 9 from ~30–50 hand-labeled docs |

## Quality workflow — every step, no exceptions

1. **Implement minimal** — smallest clean code that does the job; no speculative abstractions, no dead code.
2. **Verify, don't assume** — check every API/library claim against the installed package/docs before relying on it; on catching an assumption, stop and recalibrate.
3. **Independent review, every time** — fresh review agent(s) on the step's diff before commit: correctness, minimalism (flag anything deletable), production readiness (errors, encodings, security, Windows paths). Fix or explicitly rebut every finding.
4. **Tests green** — full `pytest`, including the step's new tests.
5. **Then commit** — one commit per step, only after 1–4.

## Steps

- [x] **0. Housekeeping** — this file; quality rules to memory; independent review of pre-existing code (skeleton + `agent/parsing.py` — not grandfathered); first commit. *Review fixed: RecursionError + lone-surrogate contract breaks, output/ gitignore gap, duplicate string parsers, dead constant, stale status, pydantic<3 cap.*
- [x] **1. Contract v2** — `DocumentContent(text, pages)` in `agent/schema.py` (+ `.is_empty`); `RawDocument.content`; `classify(content)`; import-rule amendment: `ingestion/` may import `agent.schema` only; `agent/schema.py` + `agent/__init__.py` stay pydantic/stdlib-only. *Review: code clean; fixed 5 doc-drift spots. Known limitation (deliberate): `DocumentContent` with real image bytes is not JSON-serializable — nothing serializes it; needs `ser_json_bytes='base64'` if that ever changes.*
- [x] **2. Ingestion** — `extractors.py`: `Extractor = Callable[[Path], DocumentContent]`, `extract_text_layer` via pypdf (empty text for scans, never an exception); `reader.py`: `list_documents` + `load_document` (generator dropped for per-doc error isolation); doc_id = source filename; committed Greek fixture PDFs (generated once, fpdf2 not a dependency); pin pypdf. *Review fixed: added `cryptography` so AES empty-password PDFs actually extract (verified); directories now land in `skipped` instead of vanishing; fixture renamed to `no_text_layer.pdf` (it has no image); stale `iter_documents` sketch in main.py; both encrypted branches now tested.*
- [x] **3. Agent LLM call** — `classify`: Sonnet, forced tool-use with schema = Decision minus `parse_errors` (drift-guard test); text and image blocks both built now; empty content → no API call, fallback decision; new `parsing.fallback_decision(note)`; transport errors raise (main.py owns them — nuance recorded in `agent/CLAUDE.md`); SYSTEM_PROMPT with company disambiguation + honest-confidence instruction; pin anthropic (python-dotenv lands in step 6 with its only consumer); mocked-client tests. *Review fixed: dropped `temperature=0` (newer models reject non-default sampling; unverifiable without a key — step 7 validates live), `thinking: disabled` set explicitly, schema Field examples aligned with prompt/parser format. Step 7 must confirm: request accepted live, no max_tokens truncation.*
- [x] **4. Routing** — thresholds 0.80 (provisional until step 9); REVIEW if company==UNKNOWN or any confidence < threshold (equality passes); reason names every trigger with numbers; rule-matrix tests. *Review fixed: THRESHOLDS↔FieldConfidence drift-guard test, stale "move" wording. Rebutted: reason strings round scores to 2dp (consistent with the CSV's %.2f columns; comparison uses full precision).*
- [x] **5. Review CSV** — `write_review_csv`: utf-8-sig, `newline=""`, delimiter as constant (Greek Excel note in review/CLAUDE.md); date ISO-or-empty, confidences `%.2f`, parse_errors joined `; `; roundtrip + BOM tests. *Review fixed: DictWriter replaces positional-by-faith column pairing (reviewer proved a silent-swap mutation passed the old tests); overwrite semantics documented; hostile-string roundtrip test added.*
- [ ] **6. Composition root** — argparse `run`/`eval`; dotenv; per-doc isolation (any exception → `fallback_decision` → review); copy with sanitized LLM paths (whitelist chars incl. Greek, traversal impossible), collision suffixes `_2, _3…`, no double extensions; `output/decisions.jsonl` (machine record for eval) + review CSV; per-doc console line + end summary; `--model` flag; mocked end-to-end test incl. hostile-filename case.
- [ ] **7. Shakedown (live)** — user drops 5–10 real PDFs + API key; run; inspect CSV/tree/summaries/cost; tune prompt only. Done when user says outputs look sane.
- [ ] **8. Eval** — `load_ground_truth` (fail loud on bad labels); decisions from jsonl; per-field accuracy; AUROC (tiny rank-based impl, no sklearn); threshold sweep 0.50–0.95 (coverage + auto-accuracy); recommendation = smallest t hitting target auto-accuracy (0.98 default); `python main.py eval`; hand-computable tests.
- [ ] **9. Calibrate** — user labels 30–50 docs; run eval; set data-driven thresholds; optional Haiku comparison; README + this file updated.

## Deliberately deferred

OCR/vision extractors (contract ready) · Batches API / resume ledger / `--only-new` · copy→move switch after trust established · threshold logic beyond per-field cutoffs.
