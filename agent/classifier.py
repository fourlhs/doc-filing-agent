"""Classify a document's text into a structured Decision via one LLM call.

Pure with respect to the world: the only input is the text string, the only
output is a Decision. No filesystem access, no paths, no folder names.
"""

from agent.schema import Decision


def classify(text: str) -> Decision:
    """Return the agent's structured Decision for one document's text.

    Never raises on malformed model output: the raw response must flow
    through ``parsing.parse_decision``, which repairs each invalid field to
    a safe fallback with confidence forced to 0 — routing then sends the
    doc to human review. A parse failure is a review-routed document, not
    an exception.

    TODO: implement after design review.
        - single LLM call (Anthropic API) with prompts.SYSTEM_PROMPT
        - constrain output to the Decision schema (structured output /
          tool-use JSON), then hand the raw payload to parse_decision
        - decide how confidence is elicited (self-reported per field vs
          derived) — eval/ will tell us if it's calibrated
    """
    raise NotImplementedError("Skeleton only — pending design review")
