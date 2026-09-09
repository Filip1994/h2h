from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

LIFECYCLE_SCHEMA_VERSION = 1
CANONICAL_SNAPSHOT_TYPES = {"OPENING", "ENTRY", "INTERMEDIATE", "T5", "CLOSING"}


def parse_capture(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        return datetime.fromisoformat(str(value)).astimezone(UTC)
    except ValueError:
        return None


def lifecycle_key(
    *, fixture_id: int, market: str, bookmaker_id: int
) -> tuple[int, str, int]:
    return int(fixture_id), str(market), int(bookmaker_id)


def _load(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    return rows


def observations_for(
    path: Path, *, fixture_id: int, market: str, bookmaker_id: int
) -> list[dict[str, Any]]:
    key = lifecycle_key(fixture_id=fixture_id, market=market, bookmaker_id=bookmaker_id)
    rows = []
    for item in _load(path):
        try:
            item_key = lifecycle_key(
                fixture_id=int(item["fixture_id"]),
                market=str(item["market"]),
                bookmaker_id=int(item["bookmaker_id"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        if item_key == key and parse_capture(item.get("odds_captured_at")) is not None:
            rows.append(item)
    rows.sort(key=lambda item: parse_capture(item["odds_captured_at"]))
    return rows


def select_opening(
    observations: list[dict[str, Any]], pick_at: datetime
) -> dict[str, Any] | None:
    pick_at = pick_at.astimezone(UTC)
    candidates = [
        item
        for item in observations
        if str(item.get("snapshot_type")) in {"OPENING", "INTERMEDIATE"}
        and (captured := parse_capture(item.get("odds_captured_at"))) is not None
        and captured <= pick_at
    ]
    return candidates[0] if candidates else None


def select_pick(
    observations: list[dict[str, Any]], pick_at: datetime
) -> dict[str, Any] | None:
    pick_at = pick_at.astimezone(UTC)
    entries = [
        item
        for item in observations
        if str(item.get("snapshot_type")) == "ENTRY"
        and parse_capture(item.get("odds_captured_at")) == pick_at
    ]
    if entries:
        return entries[-1]
    return None


def select_closing(
    observations: list[dict[str, Any]],
    kickoff: datetime,
    *,
    window_min_seconds: int = 120,
    window_max_seconds: int = 480,
) -> dict[str, Any] | None:
    kickoff = kickoff.astimezone(UTC)
    candidates: list[dict[str, Any]] = []
    for item in observations:
        captured = parse_capture(item.get("odds_captured_at"))
        if captured is None:
            continue
        seconds = (kickoff - captured).total_seconds()
        if (
            str(item.get("snapshot_type")) in {"T5", "CLOSING"}
            and window_min_seconds <= seconds <= window_max_seconds
        ):
            candidates.append(item)
    return candidates[-1] if candidates else None


def clv_from_odds(pick_odd: Any, closing_odd: Any) -> float | None:
    try:
        pick = float(pick_odd)
        closing = float(closing_odd)
    except (TypeError, ValueError):
        return None
    if pick <= 1.0 or closing <= 1.0:
        return None
    return round((pick / closing) - 1.0, 6)


def lifecycle_contract(
    observations: list[dict[str, Any]],
    *,
    pick_at: datetime,
    kickoff: datetime | None,
) -> dict[str, Any]:
    opening = select_opening(observations, pick_at)
    pick = select_pick(observations, pick_at)
    closing = select_closing(observations, kickoff) if kickoff else None
    opening_reason = None if opening else "NO_EARLIER_OBSERVATION"
    pick_reason = None if pick else "NO_EXACT_ENTRY_OBSERVATION"
    closing_reason = None if closing else (
        "NO_VALID_PRE_KICKOFF_CLOSE" if kickoff else "KICKOFF_UNAVAILABLE"
    )
    return {
        "schema_version": LIFECYCLE_SCHEMA_VERSION,
        "opening": opening,
        "pick": pick,
        "closing": closing,
        "opening_available": opening is not None,
        "pick_available": pick is not None,
        "closing_available": closing is not None,
        "opening_observation_id": opening.get("observation_id") if opening else None,
        "pick_observation_id": pick.get("observation_id") if pick else None,
        "closing_observation_id": closing.get("observation_id") if closing else None,
        "opening_unavailable_reason": opening_reason,
        "pick_unavailable_reason": pick_reason,
        "closing_unavailable_reason": closing_reason,
        "coverage": (
            "FULLY_AUDITABLE"
            if opening and pick and closing
            else "PARTIAL"
            if opening or pick or closing
            else "UNRECOVERABLE"
        ),
        "clv_odds_pct": clv_from_odds(
            pick.get("odd") if pick else None,
            closing.get("odd") if closing else None,
        ),
        "clv_available": bool(pick and closing),
        "clv_status": "COMPUTABLE" if pick and closing else "NOT_COMPUTABLE",
    }


def canonical_observation(
    *,
    fixture_id: int,
    market: str,
    bookmaker_id: int,
    bookmaker: str,
    odd: float,
    opposite_odd: float,
    captured_at: datetime,
    snapshot_type: str,
    prediction_id: str | None = None,
    signal_id: str | None = None,
    bet_id: str | None = None,
    source_endpoint: str = "odds",
    source_request_hash: str | None = None,
    captured_by: str = "UNKNOWN",
) -> dict[str, Any]:
    if snapshot_type not in CANONICAL_SNAPSHOT_TYPES:
        raise ValueError(f"Unsupported canonical snapshot type: {snapshot_type}")
    captured_iso = captured_at.astimezone(UTC).isoformat()
    identity = "|".join(
        (
            str(int(fixture_id)),
            str(market),
            str(int(bookmaker_id)),
            captured_iso,
            f"{float(odd):.4f}",
            f"{float(opposite_odd):.4f}",
            snapshot_type,
        )
    )
    observation_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return {
        "schema_version": LIFECYCLE_SCHEMA_VERSION,
        "observation_id": observation_id,
        "fixture_id": int(fixture_id),
        "market": str(market),
        "bookmaker_id": int(bookmaker_id),
        "bookmaker": str(bookmaker),
        "selection": str(market),
        "odd": round(float(odd), 4),
        "opposite_odd": round(float(opposite_odd), 4),
        "odds_captured_at": captured_iso,
        "snapshot_type": snapshot_type,
        "prediction_id": prediction_id,
        "signal_id": signal_id,
        "bet_id": bet_id,
        "source_endpoint": source_endpoint,
        "source_request_hash": source_request_hash,
        "captured_by": captured_by,
    }


def within_t5_window(captured_at: datetime, kickoff: datetime) -> bool:
    seconds = (kickoff.astimezone(UTC) - captured_at.astimezone(UTC)).total_seconds()
    return 120 <= seconds <= 480


def latest_pre_kickoff(
    observations: list[dict[str, Any]], kickoff: datetime
) -> dict[str, Any] | None:
    kickoff = kickoff.astimezone(UTC)
    candidates = [
        item
        for item in observations
        if (captured := parse_capture(item.get("odds_captured_at"))) is not None
        and captured <= kickoff
    ]
    return candidates[-1] if candidates else None
