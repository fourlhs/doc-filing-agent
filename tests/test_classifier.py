"""Tests for agent/classifier.py with a fake client — no network, no key.

The fake mimics exactly the SDK surface classifier uses: client.messages
.create(**kwargs) -> response with .content blocks and .stop_reason.
"""

import base64
from types import SimpleNamespace

import pytest

from agent import prompts
from agent.classifier import classify
from agent.schema import Company, Decision, DocType, DocumentContent

VALID_TOOL_INPUT = {
    "company": "Helector",
    "doc_type": "invoice",
    "date": "2024-03-15",
    "summary": "Τιμολόγιο της Helector.",
    "proposed_filename": "2024-03-15_helector_invoice",
    "proposed_folder": "Helector/invoice/",
    "confidence": {"company": 0.95, "doc_type": 0.9, "date": 0.85},
    "rationale": "Λογότυπος Helector στην επικεφαλίδα.",
}


class FakeClient:
    """Records create() calls; serves canned responses in order (the last
    one repeats, so single-response fakes work for any number of calls)."""

    def __init__(self, *responses):
        self.calls = []

        def create(**kwargs):
            self.calls.append(kwargs)
            return responses[min(len(self.calls) - 1, len(responses) - 1)]

        self.messages = SimpleNamespace(create=create)


def tool_response(tool_input):
    block = SimpleNamespace(type="tool_use", input=tool_input)
    return SimpleNamespace(content=[block], stop_reason="tool_use")


def test_classify_returns_decision_and_sends_forced_tool_call():
    client = FakeClient(tool_response(VALID_TOOL_INPUT))
    decision = classify(DocumentContent(text="ΤΙΜΟΛΟΓΙΟ Helector"), client=client)

    assert decision.company == Company.HELECTOR
    assert decision.doc_type == DocType.INVOICE
    assert decision.parse_errors == []
    assert decision.agreement is None  # single sample: no agreement signal

    (call,) = client.calls
    assert call["model"] == "claude-sonnet-5"
    assert call["thinking"] == {"type": "disabled"}
    assert "temperature" not in call  # newer models reject non-default sampling
    assert call["system"] == prompts.SYSTEM_PROMPT
    assert call["tools"] == [prompts.DECISION_TOOL]
    assert call["tool_choice"] == {"type": "tool", "name": "file_decision"}
    assert call["messages"] == [
        {"role": "user", "content": [{"type": "text", "text": "ΤΙΜΟΛΟΓΙΟ Helector"}]}
    ]


def test_classify_pages_become_base64_image_blocks():
    client = FakeClient(tool_response(VALID_TOOL_INPUT))
    png = b"\x89PNG fake"
    classify(DocumentContent(pages=[png]), client=client)

    (block,) = client.calls[0]["messages"][0]["content"]
    assert block["type"] == "image"
    assert block["source"]["media_type"] == "image/png"
    assert base64.standard_b64decode(block["source"]["data"]) == png


def test_classify_empty_content_skips_the_api_entirely():
    client = FakeClient(None)  # any create() call would append to .calls
    decision = classify(DocumentContent(text="   "), client=client)

    assert client.calls == []
    assert decision.company == Company.UNKNOWN
    assert decision.confidence.company == 0.0
    assert decision.parse_errors == ["no content extracted from document"]


def test_classify_no_tool_call_falls_back_not_raises():
    refusal = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="I cannot")], stop_reason="end_turn"
    )
    decision = classify(DocumentContent(text="x"), client=FakeClient(refusal))

    assert decision.company == Company.UNKNOWN
    assert decision.confidence.doc_type == 0.0
    assert decision.parse_errors == ["model returned no tool call (stop_reason=end_turn)"]


def test_classify_malformed_tool_input_degrades_via_parser():
    bad = dict(VALID_TOOL_INPUT, company="ΑΚΤΩΡ ΑΤΕ")
    decision = classify(DocumentContent(text="x"), client=FakeClient(tool_response(bad)))

    assert decision.company == Company.UNKNOWN
    assert decision.confidence.company == 0.0
    assert decision.doc_type == DocType.INVOICE  # rest of the payload intact


def test_tool_schema_tracks_decision_fields_minus_pipeline_owned():
    schema = prompts.DECISION_TOOL["input_schema"]
    expected = set(Decision.model_fields) - {"parse_errors", "agreement"}
    assert set(schema["properties"]) == expected
    assert set(schema["required"]) == expected


def test_multi_sample_agreement_measures_answer_stability():
    dissent = dict(VALID_TOOL_INPUT, company="Aktor Group")
    client = FakeClient(
        tool_response(VALID_TOOL_INPUT),
        tool_response(VALID_TOOL_INPUT),
        tool_response(dissent),
        tool_response(VALID_TOOL_INPUT),
        tool_response(VALID_TOOL_INPUT),
    )
    decision = classify(DocumentContent(text="x"), client=client, samples=5)

    assert len(client.calls) == 5
    assert decision.company == Company.HELECTOR  # sample 1 is the filed answer
    assert decision.agreement.company == 0.8  # 4 of 5 reproduced it
    assert decision.agreement.doc_type == 1.0
    assert decision.agreement.date == 1.0
    assert decision.confidence.company == 0.95  # self-report untouched


def test_malformed_sample_counts_as_disagreement():
    refusal = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="no")], stop_reason="end_turn"
    )
    client = FakeClient(
        tool_response(VALID_TOOL_INPUT),
        refusal,  # repairs to UNKNOWN/OTHER/null -> disagrees on every field
        tool_response(VALID_TOOL_INPUT),
    )
    decision = classify(DocumentContent(text="x"), client=client, samples=3)

    assert decision.parse_errors == []  # the filed (first) sample was clean
    assert decision.agreement.company == pytest.approx(2 / 3)
    assert decision.agreement.date == pytest.approx(2 / 3)


def test_token_usage_accumulates_when_responses_carry_usage(monkeypatch):
    from agent import classifier

    monkeypatch.setattr(classifier, "TOKEN_USAGE", {"input": 0, "output": 0})
    response = tool_response(VALID_TOOL_INPUT)
    response.usage = SimpleNamespace(input_tokens=100, output_tokens=40)
    classify(DocumentContent(text="x"), client=FakeClient(response), samples=2)
    assert classifier.TOKEN_USAGE == {"input": 200, "output": 80}


def test_samples_below_one_rejected():
    with pytest.raises(ValueError, match="samples must be >= 1"):
        classify(DocumentContent(text="x"), client=FakeClient(None), samples=0)
