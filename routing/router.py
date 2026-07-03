"""Route each Decision to auto-filing or human review, with a reason.

Pure: reads the Decision's per-field confidences, returns a destination.
Never touches the filesystem — main.py performs the actual move.
"""

from dataclasses import dataclass
from enum import Enum

from agent.schema import Decision

# TODO: set after eval/ shows where confidence separates right from wrong.
# None = deliberately unset; route() must refuse to run until these are chosen.
COMPANY_THRESHOLD: float | None = None
DOC_TYPE_THRESHOLD: float | None = None
DATE_THRESHOLD: float | None = None


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

    Rules (fixed by design, thresholds TBD):
        - company == UNKNOWN                          -> REVIEW
        - any field confidence below its threshold    -> REVIEW
        - otherwise                                   -> AUTO
    The reason string must name the triggering field(s) and value(s),
    e.g. "date confidence 0.42 below threshold 0.80".

    TODO: implement after design review and after thresholds are set.
    """
    raise NotImplementedError("Skeleton only — pending design review")
