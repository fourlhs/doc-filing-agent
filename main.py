"""Composition root: the ONLY place where the world (I/O) meets the brain.

Per document: ingestion loads content, the agent classifies it, routing picks
auto or review, and this file copies the original into output/ — auto docs
under their (sanitized) proposed folder and filename, review docs under their
original name. Every document lands in the review CSV (humans) and
decisions.jsonl (machines — eval/ consumes it). Copying, env loading, path
sanitization, and error swallowing live here and nowhere else.

Per-document isolation: any exception from ingestion or the LLM call becomes
a fallback Decision (confidence 0 -> review); one bad document never kills
the run. Filing paths proposed by the LLM are untrusted and are sanitized
before touching the filesystem.
"""

import argparse
import json
import re
import shutil
from itertools import count
from pathlib import Path

from dotenv import load_dotenv

from agent import classifier, parsing
from agent.schema import Decision
from eval.evaluate import evaluate, format_report, load_decisions, load_ground_truth
from ingestion import reader
from review.report import ReviewRow, write_review_csv
from routing.router import Destination, RoutingResult, route

INPUT_DIR = Path("input")
OUTPUT_DIR = Path("output")
GROUND_TRUTH_CSV = Path("data") / "ground_truth.csv"

# One path segment: \w covers Greek letters; everything else except dot,
# dash, and space becomes _. Windows-reserved device names get a prefix.
_UNSAFE = re.compile(r"[^\w. -]")
_RESERVED = {"con", "prn", "aux", "nul"} | {
    f"{d}{i}" for d in ("com", "lpt") for i in (*"0123456789", "¹", "²", "³")
}
# NTFS caps components at 255 chars; cap well below so a prompt-injected
# length bomb can never make a sanitized path unwriteable.
_MAX_COMPONENT = 120


def sanitize_component(raw: str) -> str:
    """Make one path segment filesystem-safe: no separators, no traversal
    (leading/trailing dots stripped), no Windows-invalid characters or
    reserved device names, bounded length."""
    clean = _UNSAFE.sub("_", raw).strip(" .")[:_MAX_COMPONENT].rstrip(" .")
    if clean.split(".")[0].lower() in _RESERVED:
        clean = "_" + clean
    return clean or "_"


def sanitize_folder(raw: str) -> Path:
    """LLM-proposed folder -> safe relative Path. Split on both separator
    styles; empty and dots-only segments (e.g. '..') vanish, so escaping the
    output tree is impossible by construction."""
    parts = [sanitize_component(p) for p in re.split(r"[\\/]+", raw) if p.strip(" .")]
    return Path(*parts) if parts else Path("_")


def target_filename(proposed: str, source: Path) -> str:
    """Sanitized proposed filename carrying the source's extension exactly
    once (the agent proposes extension-less names, but don't trust that)."""
    name = sanitize_component(proposed)
    if source.suffix:
        while name.lower().endswith(source.suffix.lower()):
            name = name[: -len(source.suffix)]
    return (name or "_") + source.suffix.lower()


def unique_path(path: Path) -> Path:
    """First free variant of path: name.pdf, name_2.pdf, name_3.pdf, ..."""
    if not path.exists():
        return path
    for i in count(2):
        candidate = path.with_stem(f"{path.stem}_{i}")
        if not candidate.exists():
            return candidate


def copy_to_destination(
    source: Path, decision: Decision, result: RoutingResult, output_dir: Path
) -> None:
    """Copy (never move — originals stay in input/) to the routed location."""
    if result.destination is Destination.AUTO:
        folder = output_dir / "auto" / sanitize_folder(decision.proposed_folder)
        name = target_filename(decision.proposed_filename, source)
    else:
        folder = output_dir / "review"
        name = source.name
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, unique_path(folder / name))


def place_document(
    source: Path, decision: Decision, result: RoutingResult, output_dir: Path
) -> RoutingResult:
    """Copy with per-document degradation: a failed auto-copy demotes the doc
    to review; a failed review-copy is recorded in the returned reason (the
    original is still safe in input/). Never raises for one document."""
    try:
        copy_to_destination(source, decision, result, output_dir)
        return result
    except OSError as exc:
        demoted = RoutingResult(Destination.REVIEW, f"{result.reason}; copy failed: {exc}")
        if result.destination is Destination.REVIEW:
            return demoted  # the review copy itself failed; nothing left to try
        try:
            copy_to_destination(source, decision, demoted, output_dir)
        except OSError:
            pass
        return demoted


def run(
    input_dir: Path = INPUT_DIR,
    output_dir: Path = OUTPUT_DIR,
    model: str = classifier.MODEL,
    samples: int = 1,
) -> None:
    """Process every PDF in input_dir end to end."""
    if samples < 1:
        raise SystemExit(f"--samples must be >= 1, got {samples}")
    if not input_dir.is_dir():
        raise SystemExit(f"input directory not found: {input_dir}")
    docs, skipped = reader.list_documents(input_dir)
    for path in skipped:
        print(f"skipped (not a PDF): {path.name}")

    rows: list[ReviewRow] = []
    classifier.TOKEN_USAGE.update(input=0, output=0)
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "decisions.jsonl").open("w", encoding="utf-8") as jsonl:
        for path in docs:
            try:
                raw = reader.load_document(path)
                decision = classifier.classify(raw.content, model=model, samples=samples)
            except Exception as exc:  # per-doc isolation: one bad doc != dead run
                decision = parsing.fallback_decision(f"pipeline error: {exc}")
                print(f"{path.name}: pipeline error: {exc}")
            result = place_document(path, decision, route(decision), output_dir)
            rows.append(ReviewRow(path.name, path.name, decision, result))
            jsonl.write(
                json.dumps(
                    {
                        "doc_id": path.name,
                        "decision": decision.model_dump(mode="json"),
                        "destination": result.destination.value,
                        "reason": result.reason,
                        "samples": samples,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            print(f"{path.name} -> {result.destination.value} ({result.reason})")

    review_csv = output_dir / "review_report.csv"
    write_review_csv(rows, review_csv)
    auto = sum(1 for r in rows if r.routing.destination is Destination.AUTO)
    print(f"\n{len(rows)} processed: {auto} auto, {len(rows) - auto} review")
    usage = classifier.TOKEN_USAGE
    if rows and (usage["input"] or usage["output"]):
        print(
            f"tokens: {usage['input']} in / {usage['output']} out "
            f"(avg {usage['input'] // len(rows)} in / {usage['output'] // len(rows)} out per doc)"
        )
    print(f"report: {review_csv}")


def main(argv: list[str] | None = None) -> None:
    load_dotenv()  # ANTHROPIC_API_KEY from .env, if present
    parser = argparse.ArgumentParser(description="Classify and file Greek business documents.")
    sub = parser.add_subparsers(dest="command")
    run_parser = sub.add_parser("run", help="process input/ end to end (default)")
    run_parser.add_argument("--model", default=classifier.MODEL, help="Claude model override")
    run_parser.add_argument(
        "--samples",
        type=int,
        default=1,
        help="classifications per doc; >1 records per-field sampling agreement",
    )
    eval_parser = sub.add_parser("eval", help="score decisions against ground truth")
    eval_parser.add_argument("--ground-truth", type=Path, default=GROUND_TRUTH_CSV)
    eval_parser.add_argument("--decisions", type=Path, default=OUTPUT_DIR / "decisions.jsonl")
    args = parser.parse_args(argv)

    if args.command == "eval":
        try:
            report = evaluate(load_decisions(args.decisions), load_ground_truth(args.ground_truth))
        except FileNotFoundError as exc:
            raise SystemExit(f"{exc} - run 'python main.py run' first and label docs in {GROUND_TRUTH_CSV}")
        except ValueError as exc:
            raise SystemExit(str(exc))
        print(format_report(report))
    else:
        run(
            model=getattr(args, "model", classifier.MODEL),
            samples=getattr(args, "samples", 1),
        )


if __name__ == "__main__":
    main()
