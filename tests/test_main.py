"""End-to-end tests for main.py with classify mocked — no network, no key.

Uses the committed fixture PDFs; the fake classifier mirrors the real one's
empty-content contract (fallback decision without an API call).
"""

import json
import shutil
from pathlib import Path

import pytest

import main
from agent import classifier, parsing
from agent.schema import Decision
from main import sanitize_component, sanitize_folder, target_filename

FIXTURES = Path(__file__).parent / "fixtures"

CONFIDENT = {
    "company": "Helector",
    "doc_type": "invoice",
    "date": "2024-03-15",
    "summary": "Τιμολόγιο.",
    "proposed_filename": "2024-03-15_helector_invoice",
    "proposed_folder": "Helector/invoice/",
    "confidence": {"company": 0.95, "doc_type": 0.9, "date": 0.85},
    "rationale": "Λογότυπος.",
}


def fake_classify_returning(payload):
    def fake(content, **kwargs):
        if content.is_empty:  # mirror the real classifier's no-API short-circuit
            return parsing.fallback_decision("no content extracted from document")
        return parsing.parse_decision(payload)

    return fake


@pytest.fixture
def dirs(tmp_path):
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    return input_dir, tmp_path / "out"


def test_end_to_end_files_copies_and_reports(dirs, monkeypatch, capsys):
    input_dir, output_dir = dirs
    shutil.copy(FIXTURES / "greek_text.pdf", input_dir)
    shutil.copy(FIXTURES / "no_text_layer.pdf", input_dir)
    (input_dir / "note.txt").write_text("x")
    monkeypatch.setattr(classifier, "classify", fake_classify_returning(CONFIDENT))

    main.run(input_dir, output_dir)

    auto_file = output_dir / "auto/Helector/invoice/2024-03-15_helector_invoice.pdf"
    assert auto_file.exists()
    assert auto_file.read_bytes() == (FIXTURES / "greek_text.pdf").read_bytes()
    assert (output_dir / "review/no_text_layer.pdf").exists()
    assert (input_dir / "greek_text.pdf").exists()  # copy, never move

    lines = (output_dir / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]
    assert [r["doc_id"] for r in records] == ["greek_text.pdf", "no_text_layer.pdf"]
    assert records[0]["destination"] == "auto"
    assert records[1]["destination"] == "review"
    assert records[0]["samples"] == 1
    Decision.model_validate(records[0]["decision"])  # jsonl round-trips the schema

    report = (output_dir / "review_report.csv").read_text(encoding="utf-8-sig")
    assert "greek_text.pdf" in report and "no_text_layer.pdf" in report
    assert "skipped (not a PDF): note.txt" in capsys.readouterr().out


def test_corrupt_pdf_is_isolated_not_fatal(dirs, monkeypatch):
    input_dir, output_dir = dirs
    shutil.copy(FIXTURES / "greek_text.pdf", input_dir)
    (input_dir / "broken.pdf").write_bytes(b"not a pdf")
    monkeypatch.setattr(classifier, "classify", fake_classify_returning(CONFIDENT))

    main.run(input_dir, output_dir)  # must not raise

    assert (output_dir / "review/broken.pdf").exists()
    records = [
        json.loads(line)
        for line in (output_dir / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    broken = next(r for r in records if r["doc_id"] == "broken.pdf")
    assert broken["destination"] == "review"
    assert any("pipeline error" in e for e in broken["decision"]["parse_errors"])
    assert any(r["destination"] == "auto" for r in records)  # good doc unaffected


def test_hostile_llm_paths_cannot_escape_output(dirs, monkeypatch):
    input_dir, output_dir = dirs
    shutil.copy(FIXTURES / "greek_text.pdf", input_dir)
    hostile = dict(
        CONFIDENT,
        proposed_filename="..\\..\\escape" + "A" * 300,  # length bomb included
        proposed_folder="../../../etc/" + "B" * 300,
    )
    monkeypatch.setattr(classifier, "classify", fake_classify_returning(hostile))

    main.run(input_dir, output_dir)  # must not raise (WinError 123 on long names)

    copies = [p for p in output_dir.rglob("*.pdf")]
    assert len(copies) == 1
    assert copies[0].resolve().is_relative_to((output_dir / "auto").resolve())
    relative = copies[0].relative_to(output_dir)
    assert all(len(part) <= main._MAX_COMPONENT + len(".pdf") for part in relative.parts)


def test_filename_collision_gets_numeric_suffix(dirs, monkeypatch):
    input_dir, output_dir = dirs
    shutil.copy(FIXTURES / "greek_text.pdf", input_dir / "a.pdf")
    shutil.copy(FIXTURES / "greek_text.pdf", input_dir / "b.pdf")
    monkeypatch.setattr(classifier, "classify", fake_classify_returning(CONFIDENT))

    main.run(input_dir, output_dir)

    folder = output_dir / "auto/Helector/invoice"
    assert sorted(p.name for p in folder.iterdir()) == [
        "2024-03-15_helector_invoice.pdf",
        "2024-03-15_helector_invoice_2.pdf",
    ]


def test_missing_input_dir_exits_cleanly(tmp_path):
    with pytest.raises(SystemExit, match="input directory not found"):
        main.run(tmp_path / "nope", tmp_path / "out")


def test_samples_below_one_exits_before_touching_outputs(dirs):
    input_dir, output_dir = dirs
    with pytest.raises(SystemExit, match="--samples must be >= 1"):
        main.run(input_dir, output_dir, samples=0)
    assert not output_dir.exists()  # previous run's records never clobbered


def test_run_forwards_samples_and_jsonl_carries_agreement(dirs, monkeypatch):
    input_dir, output_dir = dirs
    shutil.copy(FIXTURES / "greek_text.pdf", input_dir)
    seen = {}

    def fake(content, samples=1, **kwargs):
        seen["samples"] = samples
        decision = parsing.parse_decision(CONFIDENT)
        from agent.schema import FieldConfidence

        return decision.model_copy(
            update={"agreement": FieldConfidence(company=0.8, doc_type=1.0, date=0.6)}
        )

    monkeypatch.setattr(classifier, "classify", fake)
    main.run(input_dir, output_dir, samples=5)

    assert seen["samples"] == 5
    (line,) = (output_dir / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
    record = json.loads(line)
    assert record["samples"] == 5
    restored = Decision.model_validate(record["decision"])
    assert restored.agreement.company == 0.8  # agreement round-trips the jsonl


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Helector", "Helector"),
        ("..", "_"),
        ("a<b>:c|d?.pdf", "a_b__c_d_.pdf"),
        ("CON", "_CON"),
        ("  .hidden.  ", "hidden"),
        ("Ακίνητα 2024", "Ακίνητα 2024"),
        ("", "_"),
    ],
)
def test_sanitize_component(raw, expected):
    assert sanitize_component(raw) == expected


def test_sanitize_folder_kills_traversal_and_separators():
    assert sanitize_folder("../../etc//passwd") == Path("etc/passwd")
    assert sanitize_folder("A/../B") == Path("A/B")
    assert sanitize_folder("..") == Path("_")
    assert sanitize_folder("Helector\\invoice\\") == Path("Helector/invoice")


def test_target_filename_never_doubles_the_extension():
    src = Path("x.PDF")
    assert target_filename("report", src) == "report.pdf"
    assert target_filename("report.pdf", src) == "report.pdf"
    assert target_filename("report.PDF", src) == "report.pdf"
    assert target_filename("report.pdf.pdf", src) == "report.pdf"
    assert target_filename("pdf.pdf", src) == "pdf.pdf"  # stem survives
    assert target_filename("x", Path("noext")) == "x"  # suffix-less source


def test_cli_no_args_defaults_to_run(monkeypatch):
    called = {}
    monkeypatch.setattr(main, "run", lambda **kw: called.update(kw))
    main.main([])
    assert called == {"model": classifier.MODEL, "samples": 1}


def test_cli_forwards_model_and_samples(monkeypatch):
    called = {}
    monkeypatch.setattr(main, "run", lambda **kw: called.update(kw))
    main.main(["run", "--model", "claude-haiku-4-5-20251001", "--samples", "5"])
    assert called == {"model": "claude-haiku-4-5-20251001", "samples": 5}


def test_cli_eval_prints_a_report(dirs, monkeypatch, capsys, tmp_path):
    input_dir, output_dir = dirs
    shutil.copy(FIXTURES / "greek_text.pdf", input_dir)
    monkeypatch.setattr(classifier, "classify", fake_classify_returning(CONFIDENT))
    main.run(input_dir, output_dir)

    gt = tmp_path / "gt.csv"
    gt.write_text(
        "doc_id,true_company,true_doc_type,true_date\ngreek_text.pdf,Helector,invoice,2024-03-15\n",
        encoding="utf-8",
    )
    main.main(
        ["eval", "--ground-truth", str(gt), "--decisions", str(output_dir / "decisions.jsonl")]
    )
    out = capsys.readouterr().out
    assert "scored 1 documents" in out
    assert "company: accuracy 100.0%" in out
    assert "recommended threshold" in out
