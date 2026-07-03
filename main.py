"""Composition root: the ONLY place where the world (I/O) meets the brain (agent).

Wires the pipeline together:
    1. ingestion  — read docs from input/, extract content
    2. agent      — classify content -> Decision
    3. routing    — Decision -> auto | review, with reason
    4. (here)     — move the original file to output/<destination>/
    5. review     — write the human-readable CSV report
    6. eval       — optional: score against data/ground_truth.csv

File moves happen HERE, not in routing/ — routing only decides, it never
touches the filesystem. This keeps every module below main.py swappable.
"""

from pathlib import Path

INPUT_DIR = Path("input")
REVIEW_CSV = Path("output") / "review_report.csv"
GROUND_TRUTH_CSV = Path("data") / "ground_truth.csv"


def run_pipeline(input_dir: Path = INPUT_DIR) -> None:
    """Process every document in ``input_dir`` end to end.

    TODO: implement after design review. Sketch:
        docs, skipped = ingestion.reader.list_documents(input_dir)
        for path in docs:  # per-doc try/except: one bad doc never kills the run
            raw_doc = ingestion.reader.load_document(path)
            decision = agent.classifier.classify(raw_doc.content)
            result = routing.router.route(decision)
            # copy path to output/<result.destination>/... (sanitized names)
        review.report.write_review_csv(..., REVIEW_CSV)
    """
    raise NotImplementedError("Skeleton only — pending design review")


if __name__ == "__main__":
    run_pipeline()
