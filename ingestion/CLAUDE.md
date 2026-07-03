# ingestion/

**Single responsibility:** read a document from the local `input/` folder and
extract its text. Nothing else.

- This is the ONLY module that reads raw documents from the world. Swapping
  local folder -> cloud storage (S3, SharePoint, ...) means rewriting this
  module and nothing else.
- Output contract: `RawDocument(doc_id, source_name, text)` — plain text,
  no interpretation, no classification.
- Never imports from `agent/`, `routing/`, `review/`, or `eval/`.

Input is printed Greek documents (scans/PDFs). Extraction method is an open
TODO: text-layer PDF extraction vs OCR (Tesseract `ell`). Decide after looking
at real samples.
