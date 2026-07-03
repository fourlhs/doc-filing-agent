# ingestion/

**Single responsibility:** read a document from the local `input/` folder and
extract its content. Nothing else.

- This is the ONLY module that reads raw documents from the world. Swapping
  local folder -> cloud storage (S3, SharePoint, ...) means rewriting this
  module and nothing else.
- Output contract: `RawDocument(doc_id, source_name, content)` where content
  is an `agent.schema.DocumentContent` (text and/or page images) — no
  interpretation, no classification.
- Imports `agent.schema` (the contract) and nothing else from `agent/`;
  never imports `routing/`, `review/`, or `eval/`.

Input is printed Greek documents (PDFs). v1 extraction is the pypdf text
layer (locked decision, see `docs/ROADMAP.md`); OCR/vision extractors can be
added later behind the same `DocumentContent` contract without touching any
other module.
