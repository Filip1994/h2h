from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import Settings

STRONG_SIGNAL = "STRONG_SIGNAL"
NEAR_MISS = "NEAR_MISS"
OBSERVED = "OBSERVED"


@dataclass(frozen=True)
class SignalClassification:
    signal_class: str
    qualified_candidate: bool
    near_miss_reason: str | None


def classify_signal(
    *,
    expected_value: float,
    probability_edge: float,
    stake: float,
    settings: Settings,
) -> SignalClassification:
    """Apply the existing Strong/Near-Miss semantics exactly once."""
    ev = float(expected_value)
    edge = float(probability_edge)
    stake_value = float(stake)
    qualified = ev >= settings.min_ev and edge >= settings.min_edge
    strong = (
        ev >= settings.strong_signal_min_ev
        and edge >= settings.strong_signal_min_edge
        and stake_value >= settings.strong_signal_min_stake
    )
    if strong:
        return SignalClassification(STRONG_SIGNAL, qualified, None)

    near_ev = ev >= settings.min_ev - 0.03
    near_edge = edge >= settings.min_edge - 0.02
    if near_ev or near_edge:
        if near_ev and near_edge:
            reason = "EV_AND_EDGE_NEAR_THRESHOLD"
        elif near_ev:
            reason = "EV_NEAR_THRESHOLD"
        else:
            reason = "EDGE_NEAR_THRESHOLD"
        return SignalClassification(NEAR_MISS, qualified, reason)
    return SignalClassification(OBSERVED, qualified, None)


def classification_fields(classification: SignalClassification) -> dict[str, Any]:
    return {
        "signal_class": classification.signal_class,
        "qualified_candidate": classification.qualified_candidate,
        "near_miss_reason": classification.near_miss_reason,
    }
