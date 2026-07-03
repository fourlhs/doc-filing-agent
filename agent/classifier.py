"""Classify a document's content into a structured Decision via one LLM call.

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
from agent.schema import Decision, DocumentContent

MODEL = "claude-sonnet-5"
MAX_TOKENS = 1500

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
) -> Decision:
    """Return the agent's structured Decision for one document's content.

    One LLM call with forced tool-use; the tool input flows through
    parsing.parse_decision, so malformed model output degrades to
    confidence 0 (-> human review), never an exception. Empty content
    short-circuits to a fallback Decision without spending an API call.

    ``client`` is injectable for tests; ``model`` is overridable for the
    eval-driven model comparison (docs/ROADMAP.md step 9).
    """
    if content.is_empty:
        return parsing.fallback_decision("no content extracted from document")

    # No temperature: newer Claude models reject non-default sampling params.
    # Thinking off: single-shot schema-forced classification doesn't need it,
    # and thinking tokens would count against MAX_TOKENS.
    response = (client or _default_client()).messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        thinking={"type": "disabled"},
        system=prompts.SYSTEM_PROMPT,
        messages=[{"role": "user", "content": _content_blocks(content)}],
        tools=[prompts.DECISION_TOOL],
        tool_choice={"type": "tool", "name": prompts.DECISION_TOOL["name"]},
    )
    for block in response.content:
        if block.type == "tool_use":
            return parsing.parse_decision(block.input)
    return parsing.fallback_decision(
        f"model returned no tool call (stop_reason={response.stop_reason})"
    )
