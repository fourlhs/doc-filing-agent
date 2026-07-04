"""Classify a document's content into a structured Decision — one LLM call
per sample (k identical calls on multi-sample runs).

Pure with respect to the world: the only input is a DocumentContent (text
and/or page images), the only output is a Decision. No filesystem access,
no paths, no folder names.

Error contract: malformed MODEL OUTPUT never raises (parsing.parse_decision
repairs it, confidence 0 routes to review). TRANSPORT errors (auth, rate
limit, network) DO raise — main.py's per-document isolation owns those.
"""

import base64
from typing import Any

import anthropic

from agent import parsing, prompts
from agent.schema import Decision, DocumentContent, FieldConfidence

MODEL = "claude-sonnet-5"
MAX_TOKENS = 1500

# Telemetry only (cost visibility): accumulated per API call, reset and
# reported by main.py per run. Never read by any decision logic.
TOKEN_USAGE = {"input": 0, "output": 0}

_client: anthropic.Anthropic | None = None


def _default_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    return _client


def _content_blocks(content: DocumentContent) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if content.text and content.text.strip():
        blocks.append({"type": "text", "text": content.text})
    for page in content.pages:
        blocks.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.standard_b64encode(page).decode("ascii"),
                },
            }
        )
    return blocks


def classify(
    content: DocumentContent,
    *,
    model: str = MODEL,
    client: anthropic.Anthropic | None = None,
    samples: int = 1,
) -> Decision:
    """Return the agent's structured Decision for one document's content.

    Forced tool-use; each response's tool input flows through
    parsing.parse_decision, so malformed model output degrades to
    confidence 0 (-> human review), never an exception. Empty content
    short-circuits to a fallback Decision without spending an API call.

    ``samples`` > 1 runs k identical calls: the FIRST sample is the filed
    Decision, and ``agreement`` records per field the fraction of all k
    samples that reproduce its value — an empirical P(same answer again).
    A malformed sample repairs to UNKNOWN/OTHER/null and so counts as
    disagreement — unless the filed value is itself that fallback, where
    the repair is indistinguishable from a real match and earns agreement
    credit. Measurement only: routing reads ``confidence``, never
    ``agreement``.

    ``client`` is injectable for tests; ``model`` is overridable for the
    eval-driven model comparison (docs/ROADMAP.md step 9).
    """
    if samples < 1:
        raise ValueError(f"samples must be >= 1, got {samples}")
    if content.is_empty:
        return parsing.fallback_decision("no content extracted from document")

    resolved = client or _default_client()
    decisions = [_classify_once(content, model, resolved) for _ in range(samples)]
    if samples == 1:
        return decisions[0]
    agreement = FieldConfidence(
        company=_agreement(decisions, "company"),
        doc_type=_agreement(decisions, "doc_type"),
        date=_agreement(decisions, "date"),
    )
    return decisions[0].model_copy(update={"agreement": agreement})


def _classify_once(
    content: DocumentContent, model: str, client: anthropic.Anthropic
) -> Decision:
    # No temperature: newer Claude models reject non-default sampling params
    # (and default sampling is what makes multi-sample agreement meaningful).
    # Thinking off: single-shot schema-forced classification doesn't need it,
    # and thinking tokens would count against MAX_TOKENS.
    response = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        thinking={"type": "disabled"},
        system=prompts.SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _content_blocks(content)}],
        tools=[prompts.DECISION_TOOL],
        tool_choice={"type": "tool", "name": prompts.DECISION_TOOL["name"]},
    )
    usage = getattr(response, "usage", None)
    if usage is not None:
        TOKEN_USAGE["input"] += usage.input_tokens
        TOKEN_USAGE["output"] += usage.output_tokens
    for block in response.content:
        if block.type == "tool_use":
            return parsing.parse_decision(block.input)
    return parsing.fallback_decision(
        f"model returned no tool call (stop_reason={response.stop_reason})"
    )


def _agreement(decisions: list[Decision], field: str) -> float:
    """Fraction of samples matching the filed (first) sample's value."""
    first = getattr(decisions[0], field)
    return sum(getattr(d, field) == first for d in decisions) / len(decisions)
