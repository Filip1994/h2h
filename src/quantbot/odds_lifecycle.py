from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .observation_identity import (
    canonical_observation_id,
    observation_identity_metadata,
)

LIFECYCLE_SCHEMA_VERSION = 4
CANONICAL_SNAPSHOT_TYPES = {"OPENING", "ENTRY", "INTERMEDIATE", "T15", "CLOSING", "T5"}
CLOSING_MIN_SECONDS = 10 * 60
CLOSING_MAX_SECONDS = 20 * 60


def parse_capture(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        return datetime.fromisoformat(str(value)).astimezone(UTC)
    except (TypeError, ValueError):
        return None


def _norm_selection(value: Any) -> str:
    return str(value or "").strip()


def row_observation_id(item: dict[str, Any]) -> str | None:
    if item.get("observation_id"):
        return str(item["observation_id"])
    try:
        return canonical_observation_id(
            fixture_id=int(item["fixture_id"]),
            market=str(item["market"]),
            bookmaker_id=int(item["bookmaker_id"]),
            selection=_norm_selection(item.get("selection") or item["market"]),
            odd=float(item["odd"]),
            opposite_odd=float(item["opposite_odd"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _with_identity(item: dict[str, Any]) -> dict[str, Any]:
    identity = row_observation_id(item)
    if not identity or item.get("observation_id") == identity:
        return item
    enriched = dict(item)
    enriched["observation_id"] = identity
    enriched["observation_identity_version"] = 1
    return enriched


def lifecycle_key(*, fixture_id: int, market: str, bookmaker_id: int, selection: str) -> tuple[int, str, int, str]:
    return int(fixture_id), str(market), int(bookmaker_id), _norm_selection(selection)


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
                rows.append(_with_identity(item))
    return rows


def observations_for(path: Path, *, fixture_id: int, market: str, bookmaker_id: int, selection: str | None = None) -> list[dict[str, Any]]:
    selection_norm = _norm_selection(selection or market)
    key = lifecycle_key(fixture_id=fixture_id, market=market, bookmaker_id=bookmaker_id, selection=selection_norm)
    rows = []
    for item in _load(path):
        try:
            item_key = lifecycle_key(
                fixture_id=int(item["fixture_id"]),
                market=str(item["market"]),
                bookmaker_id=int(item["bookmaker_id"]),
                selection=str(item.get("selection") or item["market"]),
            )
        except (KeyError, TypeError, ValueError):
            continue
        if item_key == key and parse_capture(item.get("odds_captured_at")) is not None:
            rows.append(item)
    rows.sort(key=lambda item: parse_capture(item["odds_captured_at"]))
    return rows


def select_first_seen(observations: list[dict[str, Any]]) -> dict[str, Any] | None:
    return observations[0] if observations else None


def select_opening(observations: list[dict[str, Any]], pick_at: datetime) -> dict[str, Any] | None:
    del pick_at
    return select_first_seen(observations)


def select_pick(observations: list[dict[str, Any]], pick_at: datetime) -> dict[str, Any] | None:
    pick_at = pick_at.astimezone(UTC)
    entries = [item for item in observations if str(item.get("snapshot_type")) == "ENTRY" and parse_capture(item.get("odds_captured_at")) == pick_at]
    return entries[-1] if entries else None


def select_live(observations: list[dict[str, Any]], *, build_at: datetime, kickoff: datetime | None) -> dict[str, Any] | None:
    build_at = build_at.astimezone(UTC)
    cutoff = min(build_at, kickoff.astimezone(UTC)) if kickoff else build_at
    candidates = [item for item in observations if (captured := parse_capture(item.get("odds_captured_at"))) is not None and captured <= cutoff]
    return candidates[-1] if candidates else None


def select_closing(observations: list[dict[str, Any]], kickoff: datetime, *, pick_at: datetime | None = None, window_min_seconds: int = CLOSING_MIN_SECONDS, window_max_seconds: int = CLOSING_MAX_SECONDS) -> dict[str, Any] | None:
    """Select the nearest persisted exact-bookmaker quote to T-15m."""
    kickoff = kickoff.astimezone(UTC)
    pick_at = pick_at.astimezone(UTC) if pick_at else None
    candidates: list[tuple[float, datetime, dict[str, Any]]] = []
    for item in observations:
        captured = parse_capture(item.get("odds_captured_at"))
        if captured is None or captured > kickoff:
            continue
        if pick_at is not None and captured <= pick_at:
            continue
        seconds = (kickoff - captured).total_seconds()
        if not window_min_seconds <= seconds <= window_max_seconds:
            continue
        candidates.append((abs(seconds - 15 * 60), captured, item))
    if not candidates:
        return None
    candidates.sort(key=lambda value: (value[0], value[1]))
    return candidates[0][2]


def clv_from_odds(pick_odd: Any, closing_odd: Any) -> float | None:
    try:
        pick = float(pick_odd)
        closing = float(closing_odd)
    except (TypeError, ValueError):
        return None
    if pick <= 1.0 or closing <= 1.0:
        return None
    return round((pick / closing) - 1.0, 6)


def _timeline_key(item: dict[str, Any]) -> str:
    if item.get("snapshot_id"):
        return str(item["snapshot_id"])
    captured = parse_capture(item.get("odds_captured_at"))
    return captured.isoformat() if captured else json.dumps(item, sort_keys=True, separators=(",", ":"))


def _timeline_entry(item: dict[str, Any], marker: str | None = None) -> dict[str, Any]:
    return {
        "observation_id": row_observation_id(item),
        "snapshot_id": item.get("snapshot_id"),
        "odd": item.get("odd"),
        "opposite_odd": item.get("opposite_odd"),
        "captured_at": item.get("odds_captured_at"),
        "snapshot_type": item.get("snapshot_type"),
        "bookmaker_id": item.get("bookmaker_id"),
        "bookmaker": item.get("bookmaker"),
        "selection": item.get("selection"),
        "marker": marker,
    }


def lifecycle_contract(observations: list[dict[str, Any]], *, pick_at: datetime, kickoff: datetime | None, build_at: datetime | None = None) -> dict[str, Any]:
    build_at = (build_at or datetime.now(UTC)).astimezone(UTC)
    first_seen = select_first_seen(observations)
    pick = select_pick(observations, pick_at)
    live = select_live(observations, build_at=build_at, kickoff=kickoff) if kickoff else select_live(observations, build_at=build_at, kickoff=None)
    closing = select_closing(observations, kickoff, pick_at=pick_at) if kickoff else None
    timeline_source = [item for item in observations if (captured := parse_capture(item.get("odds_captured_at"))) is not None and captured <= build_at and (kickoff is None or captured <= kickoff)]
    markers: dict[str, str] = {}
    if first_seen:
        markers[_timeline_key(first_seen)] = "FIRST_SEEN"
    if pick:
        markers[_timeline_key(pick)] = "PICK"
    if live:
        markers[_timeline_key(live)] = "LIVE"
    if closing:
        markers[_timeline_key(closing)] = "CLOSE_T15"
    timeline = [_timeline_entry(item, markers.get(_timeline_key(item))) for item in timeline_source]
    return {
        "schema_version": LIFECYCLE_SCHEMA_VERSION,
        "observation_identity": observation_identity_metadata(),
        "first_seen": first_seen,
        "pick": pick,
        "live": live,
        "closing": closing,
        "first_seen_available": first_seen is not None,
        "pick_available": pick is not None,
        "live_available": live is not None,
        "closing_available": closing is not None,
        "first_seen_observation_id": row_observation_id(first_seen) if first_seen else None,
        "pick_observation_id": row_observation_id(pick) if pick else None,
        "live_observation_id": row_observation_id(live) if live else None,
        "closing_observation_id": row_observation_id(closing) if closing else None,
        "live_captured_at": live.get("odds_captured_at") if live else None,
        "closing_recovered": False,
        "closing_snapshot_type": closing.get("snapshot_type") if closing else None,
        "closing_target": "T-15m (10-20m capture window)",
        "first_seen_unavailable_reason": None if first_seen else "NO_PERSISTED_OBSERVATION",
        "pick_unavailable_reason": None if pick else "NO_EXACT_ENTRY_OBSERVATION",
        "live_unavailable_reason": None if live else "NO_VALID_PRE_KICKOFF_OBSERVATION_AT_BUILD",
        "closing_unavailable_reason": None if closing else ("NO_VALID_T15_CLOSE" if kickoff else "KICKOFF_UNAVAILABLE"),
        "coverage": "FULLY_AUDITABLE" if first_seen and pick and closing else "PARTIAL" if first_seen or pick or live or closing else "UNRECOVERABLE",
        "clv_odds_pct": clv_from_odds(pick.get("odd") if pick else None, closing.get("odd") if closing else None),
        "clv_available": bool(pick and closing),
        "clv_status": "COMPUTABLE" if pick and closing else "NOT_COMPUTABLE",
        "timeline": timeline,
    }


def canonical_observation(*, fixture_id: int, market: str, bookmaker_id: int, bookmaker: str, odd: float, opposite_odd: float, captured_at: datetime, snapshot_type: str, selection: str | None = None, prediction_id: str | None = None, signal_id: str | None = None, bet_id: str | None = None, source_endpoint: str = "odds", source_request_hash: str | None = None, captured_by: str = "UNKNOWN") -> dict[str, Any]:
    if snapshot_type not in CANONICAL_SNAPSHOT_TYPES:
        raise ValueError(f"Unsupported canonical snapshot type: {snapshot_type}")
    captured_iso = captured_at.astimezone(UTC).isoformat()
    selection_norm = _norm_selection(selection or market)
    observation_id = canonical_observation_id(fixture_id=fixture_id, market=market, bookmaker_id=bookmaker_id, selection=selection_norm, odd=odd, opposite_odd=opposite_odd)
    return {
        "schema_version": LIFECYCLE_SCHEMA_VERSION,
        "observation_id": observation_id,
        "observation_identity_version": 1,
        "fixture_id": int(fixture_id),
        "market": str(market),
        "bookmaker_id": int(bookmaker_id),
        "bookmaker": str(bookmaker),
        "selection": selection_norm,
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
    return CLOSING_MIN_SECONDS <= seconds <= CLOSING_MAX_SECONDS


def latest_pre_kickoff(observations: list[dict[str, Any]], kickoff: datetime) -> dict[str, Any] | None:
    return select_live(observations, build_at=kickoff, kickoff=kickoff)
