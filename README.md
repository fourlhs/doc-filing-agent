# doc-filing-agent

A reliability-focused pipeline that reads a Greek business document, classifies it, and proposes where to file it, deferring to a human whenever it isn't sure. Built for a real law-office task where filing a document under the wrong company is expensive, so the interesting problem isn't classification, it's knowing when the model is about to be confidently wrong.

## The problem

A law office at a large corporate group receives documents (contracts, invoices, court filings, permits, correspondence) and files each one under the right subsidiary in the right folder. It's repetitive, rule-shaped, and constant. It's also unforgiving: a document filed under the wrong company is a real problem, not a typo. So an automated filer is only useful if it can tell the difference between "I'm sure" and "I'm guessing," and hand the guesses to a person instead of acting on them.

That framing drove the whole design. This is not "an LLM that classifies documents." It's a system built to fail safely on the errors that cost something.

## What it does

For each document it produces a structured decision: the company it belongs to (from a fixed list, or `UNKNOWN`), the document type (from a fixed set, or `OTHER`), the date, a short summary, a proposed filename and folder, and a confidence for each field. A routing layer then reads those confidences: if every field is confident, the document is auto-filed; if any field is uncertain or the company is `UNKNOWN`, it goes to a review queue with the reason. Nothing is filed without meeting the bar. In this version the agent proposes; a human confirms.

## Design

**Decouple the brain from the world.** The reasoning core is fully separated from file I/O. `ingestion/` is the only module that touches documents; `agent/` does no I/O except the model call; `routing/`, `eval/`, and `review/` import only the shared `Decision` schema and nothing else from the agent. Swapping the local input folder for cloud storage later rewrites one module and touches nothing else.

**The schema is the contract.** Every downstream module depends on the structured `Decision`, not on the model's prose. That's what makes the output checkable field by field, and it's where the per-field confidence lives.

**Confidence is per field, not per document.** The model can be sure about the type and unsure about the company. Routing acts on each field independently, so it flags only what's actually shaky.

**Fixed control flow, on purpose.** This is a structured pipeline with a confidence-gated review step, not an autonomous planning agent. I kept the control flow fixed deliberately: the documents are structured enough that a planning loop would add fragility without improving accuracy, and the data below backs that choice up rather than assuming it.

## Results (synthetic data)

Evaluated on 22 hand-labeled Greek documents (15 clean, 7 deliberate hard cases), using Claude Sonnet 5, ~1.5 cents per document at standard pricing.

- Company: 100%. Document type: 100%. Date: 100%.
- All auto-filed documents were fully correct. The review queue held the three `UNKNOWN` documents — unresolvable by design — plus two edge cases the model had actually answered correctly but wasn't sure about. Hesitating on a right answer is the cheap mistake; the system made no expensive ones.

**Read the 100% honestly.** Perfect scores on 22 clean-ish synthetic documents mean the task wasn't hard enough to find the model's ceiling, not that the model is perfect. Synthetic documents are more uniform than real scans. The real test is running this on actual office documents, where I expect the failures, and that's the interesting next step, not a formality.

## Findings

The confidence and evaluation work is where this got interesting, and two results were counterintuitive.

**Sample-agreement confidence failed, and the reason matters.** The Anthropic API doesn't expose token logprobs, so I substituted k=5 sampling and measured how often the five runs agreed, expecting disagreement to flag uncertainty. It came back at chance (AUROC ~0.48). The reason: the model reproduced its errors identically across all five samples. The mistakes were systematic beliefs, not sampling noise. Self-consistency only detects *stochastic* uncertainty, the model wavering. It's blind to *confident, stable* errors, which are exactly the dangerous ones. So agreement-based confidence can't see the failures that matter most on this task. (Raising sampling temperature to force diversity isn't an option either: the model rejects non-default temperature values, verified live.)

**Self-reported confidence worked.** The model's own stated per-field confidence separated its right answers from its wrong ones well (AUROC 0.88 to 0.98), dipping on precisely the answers that were wrong. On this task the model's introspection caught the systematic errors that sampling could not. So the production path is a single call with self-reported confidence, and the 5x sampling cost buys nothing.

**A confidently-wrong error, caught by the eval and fixed at the source.** Early on, documents naming an unlisted entity were being silently mapped to the nearest listed company and auto-filed. That's the single most expensive failure mode for a law office: confident, wrong, and acted on. The eval surfaced it (doc_12), and I fixed it in the prompt so unlisted entities resolve to `UNKNOWN` and route to review instead of being forced into a real company. This is the kind of error where being wrong safely matters more than being right often.

**The eval caught two problems in my own setup, not the model's.** First, a labeling error: doc_06 states only "February 2024" with no day, the model correctly assigned low confidence and flagged it, and my ground truth had claimed a specific day it couldn't have known. I resolved it by codifying a convention (month-year dates normalize to the first of the month) in three places at once, the ground truth, the system prompt, and the eval contract, so the target is defined consistently everywhere.

Second, and more subtle: my first version of that prompt used doc_06's own month as the worked example when teaching the convention. That's an answer key leaking into the calibration set, the model had effectively been shown the answer for the one document I was using to judge it. After swapping the worked example to neutral dates, doc_06 still generalizes the convention correctly, but its date confidence drops from an example-inflated 0.85 to a real 0.60–0.70 across re-runs, so it keeps routing to review. Correct answer, conservative routing, which is the right failure direction. Catching an evaluation leak in your own prompt is the kind of contamination that silently inflates results, and it only showed up because I was checking.

## Design decisions from the data

- **Single call, self-reported confidence** for production. Justified by the AUROC comparison above, not assumed.
- **Company confidence threshold raised from 0.80 to 0.90** after calibrating against results, because company is the field where a wrong auto-file costs the most. Type and date stay at 0.80 pending more data.
- **Date convention codified in three places.** Month-year dates normalize to the first of the month, defined identically in the ground truth, the system prompt, and the eval, so "correct" means the same thing everywhere. More labeled month-year documents can lift doc_06's conservative confidence later via a threshold sweep.
- **No retry or sampling loop.** The data shows sampling doesn't help here and self-report already detects the errors, so a retry mechanism would be unjustified complexity. Restraint backed by evidence.
- **Malformed or out-of-enum model output never crashes.** The field gets confidence 0 and routes to review. A reliability system should defer on bad output, not fall over.

## Limitations

- Evaluated on synthetic documents, which are cleaner and more uniform than real scans. The numbers will drop on real data, and that's expected.
- The agent proposes; originals are never moved or modified. Confident documents are *copied* into a staging `output/` tree; filing into the office's real folder structure is a deliberate later step, not something to auto-run against a live folder yet.
- Tuned to one office's companies and document types. The lists are configuration, but the thresholds are calibrated on this set.
- Self-reported confidence is not a calibrated probability. It worked well here as an error detector, but it's the model grading itself, and that can break on harder inputs.

## Next steps

- Run it on real office documents. This is the one that matters, and it's where the real story is.
- A targeted re-investigation step on low-confidence fields (re-read focused only on the date, or on disambiguating two candidate companies) is the one agentic addition justified by the actual failure mode. Optional, and only if it measurably helps.
- A cheap local model or rules for the obvious high-volume cases, with the model reserved for ambiguous ones, as the cost-at-scale answer.
- Cloud storage integration (Drive or the office's system), which the decoupled architecture makes a one-module change.

## Setup

```bash
pip install -r requirements.txt
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env   # loaded by main.py (a plain env var works too)
```

Put documents in `input/`, then:

```bash
python main.py                   # classify + route: copies into output/auto/ and output/review/, writes the review CSV
python main.py run --samples 5   # measurement mode: adds k-sample agreement per field (used for the findings above)
python main.py eval              # scores output/decisions.jsonl against data/ground_truth.csv, prints AUROC + threshold sweeps
pytest                           # 107 tests, all offline (the API is mocked)
```

## Layout

```
ingestion/   read a document, extract text (text-layer PDF; OCR/vision path swappable)
agent/       the reasoning core: schema (the shared contract), prompts, the model call
routing/     confidence gate; decides auto vs review, never touches files
eval/        scores output against hand-labeled ground truth
review/      human-readable CSV of every decision, its confidences, and its flag
main.py      composition root: the one place where decisions become file actions
```
