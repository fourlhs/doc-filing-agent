# doc-filing-agent

AI agent that reads printed Greek business documents, classifies them (company,
doc type, date), and proposes where to file them — deferring to a human reviewer
when it is not confident.

## Architecture principle: decouple the brain from the world

The reasoning core (`agent/`) must never know where documents come from or where
they go. It takes **`DocumentContent` in** (text and/or page images) and returns
a **structured `Decision` out**. Nothing else. This means the input source can be
swapped from a local folder to cloud storage — or the extraction method from
text layer to OCR/vision — by replacing `ingestion/` only; no other module changes.

### Import rules (enforce these in review)

| Module       | May import from                          | Must NEVER import from                  |
|--------------|------------------------------------------|-----------------------------------------|
| `ingestion/` | stdlib, extraction libs, `agent.schema`  | rest of `agent/`, `routing/`, `review/`, `eval/`|
| `agent/`     | stdlib, pydantic, LLM SDK                | `ingestion/`, `routing/`, `review/`, `eval/` — and no file/network I/O except the LLM call |
| `routing/`   | `agent.schema` only                      | `ingestion/` — and no filesystem access |
| `eval/`      | `agent.schema`                           | `ingestion/`                            |
| `review/`    | `agent.schema`, `routing`                | `ingestion/`                            |

- `agent/schema.py` is the **shared contract**: every module depends on it
  (`DocumentContent` in, `Decision` out), never on agent internals. The brain
  itself depends on nobody. To keep the contract import-light, `agent/schema.py`
  and `agent/__init__.py` must stay pydantic/stdlib-only — importing the
  contract must never drag in the LLM SDK.
- `routing/` computes *where a doc should go* (auto vs review) as a pure
  function of the `Decision`. It never touches files.
- `main.py` is the **composition root** — the only place where the world
  (reading files, copying files, writing reports) meets the brain.

## Pipeline

```
input/  →  ingestion (extract content)  →  agent (classify → Decision)
        →  routing (auto | review + reason)  →  main.py copies file
        →  review (human-readable CSV)       →  eval (vs ground truth)
```

## Module responsibilities

Each module folder has its own `CLAUDE.md` with its single responsibility.
One module = one responsibility; if a change touches two modules' concerns,
stop and reconsider the boundary.

## Status

Being built module-by-module; `docs/ROADMAP.md` is the single source of truth
for what is implemented (checked boxes) and what is still a stub.
