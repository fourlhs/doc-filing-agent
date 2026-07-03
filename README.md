# doc-filing-agent

An AI agent that reads printed Greek business documents, classifies each one
(company, document type, date), and proposes a filename and filing folder.
Documents the agent is confident about are filed automatically; anything
uncertain is flagged for human review.

## Pipeline

```
input/                     local drop folder for scanned/printed Greek docs
  │
  ▼
ingestion/                 read file, extract text          (world: I/O)
  │        RawDocument(doc_id, source_name, text)
  ▼
agent/                     LLM classification               (brain: pure)
  │        Decision(company, doc_type, date, summary,
  │                 proposed_filename, proposed_folder,
  │                 confidence, rationale)
  ▼
routing/                   auto vs review + reason          (rules: pure)
  │        RoutingResult(destination, reason)
  ▼
main.py                    moves file to output/auto|review (world: I/O)
  │
  ├──▶ review/             human-readable CSV of all docs & decisions
  └──▶ eval/               accuracy vs hand-labeled ground truth
```

The core design rule: `agent/` (the brain) is fully decoupled from file I/O
(the world). Swapping the local `input/` folder for cloud storage means
replacing `ingestion/` only. See `CLAUDE.md` for the import rules.

## Setup

```
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

## Run

```
python main.py                # TODO: not implemented yet — skeleton only
```

## Layout

```
ingestion/    read a document from input/, extract its text
agent/        the reasoning core: text → Decision (only module that reasons)
routing/      Decision → auto/ or review/, with reason
eval/         per-field accuracy + confidence calibration vs ground truth
review/       human-readable CSV report of every doc
input/        drop folder for incoming documents
output/       auto/ and review/ destinations
data/         ground_truth.csv (hand-labeled)
main.py       composition root: wires world to brain
```
