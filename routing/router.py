"""Route each Decision to auto-filing or human review, with a reason.

Pure: reads the Decision's per-field confidences, returns a destination.
Never touches the filesystem — main.py performs the actual copy.
"""

from dataclasses import dataclass
from enum import Enum

from agent.schema import Company, Decision

# TODO(step 9): provisional values — recalibrate from eval/ once ~30-50
# hand-labeled documents exist (docs/ROADMAP.md).
THRESHOLDS = {"company": 0.80, "doc_type": 0.80, "date": 0.80}


class Destination(str, Enum):
    """Where the document goes. Values double as output/ subfolder names."""

    AUTO = "auto"
    REVIEW = "review"


@dataclass(frozen=True)
class RoutingResult:
    """Destination plus a human-readable reason naming what triggered it."""

    destination: Destination
    reason: str


def route(decision: Decision) -> RoutingResult:
    """Apply the routing rules to one Decision.

    REVIEW if company is UNKNOWN (regardless of confidence) or any field's
    confidence is strictly below its threshold (equality passes); AUTO
    otherwise. The reason names every trigger with its numbers.
    """
    triggers = []
    if decision.company == Company.UNKNOWN:
        triggers.append("company is UNKNOWN")
    for field, threshold in THRESHOLDS.items():
        score = getattr(decision.confidence, field)
        if score < threshold:
            triggers.append(
                f"{field} confidence {score:.2f} below threshold {threshold:.2f}"
            )
    if triggers:
        return RoutingResult(Destination.REVIEW, "; ".join(triggers))
    return RoutingResult(Destination.AUTO, "all confidences at or above thresholds")
