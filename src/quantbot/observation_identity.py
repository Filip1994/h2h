from __future__ import annotations

import hashlib
import json
from typing import Any

OBSERVATION_ID_VERSION = 1
OBSERVATION_ID_SEMANTICS = "QUOTE_STATE_V1"


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def observation_identity_key(
    *,
    fixture_id: int,
    market: str,
    bookmaker_id: int,
    selection: str,
    odd: float,
    opposite_odd: float,
) -> list[Any]:
    """Canonical semantic identity for one normalized bookmaker quote state.

    Time, lifecycle classification and API request provenance are deliberately
    excluded. The key identifies the quote state; immutable snapshots record
    when and from which request that state was observed.
    """
    return [
        "quantbet-observation",
        OBSERVATION_ID_VERSION,
        int(fixture_id),
        _norm_text(market),
        int(bookmaker_id),
        _norm_text(selection or market),
        f"{float(odd):.4f}",
        f"{float(opposite_odd):.4f}",
    ]


def canonical_observation_id(
    *,
    fixture_id: int,
    market: str,
    bookmaker_id: int,
    selection: str,
    odd: float,
    opposite_odd: float,
) -> str:
    payload = observation_identity_key(
        fixture_id=fixture_id,
        market=market,
        bookmaker_id=bookmaker_id,
        selection=selection,
        odd=odd,
        opposite_odd=opposite_odd,
    )
    raw = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def observation_identity_metadata() -> dict[str, Any]:
    return {
        "version": OBSERVATION_ID_VERSION,
        "semantics": OBSERVATION_ID_SEMANTICS,
        "fields": [
            "fixture_id",
            "market",
            "bookmaker_id",
            "selection",
            "odd",
            "opposite_odd",
        ],
        "excluded_fields": [
            "captured_at",
            "snapshot_type",
            "source_request_hash",
            "source_endpoint",
            "prediction_id",
            "signal_id",
            "bet_id",
        ],
    }
