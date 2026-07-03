"""Tests for agent/classifier.py with a fake client — no network, no key.

The fake mimics exactly the SDK surface classifier uses: client.messages
.create(**kwargs) -> response with .content blocks and .stop_reason.
"""

import base64
from types import SimpleNamespace

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
    """Records the create() call and returns a canned response."""

    def __init__(self, response):
        self.calls = []

        def create(**kwargs):
            self.calls.append(kwargs)
            return response

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


def test_tool_schema_tracks_decision_fields_minus_parse_errors():
    schema = prompts.DECISION_TOOL["input_schema"]
    expected = set(Decision.model_fields) - {"parse_errors"}
    assert set(schema["properties"]) == expected
    assert set(schema["required"]) == expected
