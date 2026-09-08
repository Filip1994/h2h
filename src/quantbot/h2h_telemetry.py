from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .types import H2HStats, Market

SCHEMA_VERSION = 1
SNAPSHOT_FILE = "data/h2h_snapshots.jsonl"
OUTCOME_FILE = "data/h2h_outcomes.jsonl"
VALID_STATUSES = {
    "AVAILABLE",
    "INSUFFICIENT_HISTORY",
    "NO_RECENT_HISTORY",
    "API_ERROR",
    "PARSE_ERROR",
    "NOT_REQUESTED",
}


def h2h_snapshot_id(fixture_id: int, data_cutoff: datetime) -> str:
    canonical = f"{int(fixture_id)}|{data_cutoff.astimezone(UTC).isoformat()}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def source_request_hash(endpoint: str, params: dict[str, Any]) -> str:
    canonical = json.dumps([endpoint, sorted(params.items())], ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _match_payload(record: Any) -> dict[str, Any]:
    return {
        "fixture_id": record.fixture_id,
        "date": record.date.astimezone(UTC).isoformat(),
        "league_id": record.league_id,
        "league_name": record.league_name,
        "home_id": record.home_id,
        "home_name": record.home_name,
        "away_id": record.away_id,
        "away_name": record.away_name,
        "home_goals": record.home_goals,
        "away_goals": record.away_goals,
        "halftime_home": record.halftime_home,
        "halftime_away": record.halftime_away,
    }


def build_snapshot(*, fixture_id: int, decision_timestamp: datetime, home_id: int, away_id: int, home_name: str, away_name: str, league_id: int, league: str, h2h_enabled: bool, status: str, stats: H2HStats | None = None, error: str | None = None, captured_at: datetime | None = None) -> dict[str, Any]:
    if status not in VALID_STATUSES:
        raise ValueError(f"Unknown H2H status: {status}")
    cutoff = decision_timestamp.astimezone(UTC)
    available = status == "AVAILABLE" and stats is not None
    rates: dict[str, float | None] = {Market.OVER_25.value: None, Market.UNDER_25.value: None, Market.BTTS_YES.value: None}
    matches: list[dict[str, Any]] = []
    effective_n: float | None = None
    has_recent = False
    h2h_rate: float | None = None
    h2h_n: int | None = None
    if stats is not None:
        for market, value in stats.weighted_rates.items():
            rates[market.value] = round(float(value), 6)
        h2h_n = len(stats.matches)
        effective_n = round(float(stats.effective_n), 3)
        has_recent = bool(stats.has_recent_match)
        matches = [_match_payload(record) for record in stats.matches]
        h2h_rate = rates.get(Market.UNDER_25.value)
    request_attempted = status != "NOT_REQUESTED"
    return {
        "schema_version": SCHEMA_VERSION,
        "h2h_snapshot_id": h2h_snapshot_id(fixture_id, cutoff),
        "fixture_id": int(fixture_id),
        "decision_timestamp": cutoff.isoformat(),
        "data_cutoff": cutoff.isoformat(),
        "home_id": int(home_id),
        "away_id": int(away_id),
        "home_name": home_name,
        "away_name": away_name,
        "league_id": int(league_id),
        "league": league,
        "h2h_enabled": bool(h2h_enabled),
        "h2h_available": available,
        "h2h_status": status,
        "h2h_error": error,
        "h2h_rate": h2h_rate,
        "h2h_n": h2h_n,
        "h2h_effective_n": effective_n,
        "h2h_has_recent_match": has_recent,
        "h2h_rates": rates,
        "h2h_matches": matches,
        "captured_at": (captured_at or cutoff).astimezone(UTC).isoformat(),
        "source_endpoint": "fixtures/headtohead" if request_attempted else None,
        "source_request_hash": source_request_hash("fixtures/headtohead", {"h2h": f"{home_id}-{away_id}"}) if request_attempted else None,
        "captured_by": "engine.generate",
    }


class H2HSnapshotStore:
    """Append-only H2H research store; existing snapshots are immutable."""

    def __init__(self, root: Path):
        self.path = root / SNAPSHOT_FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ids = self._load_ids()

    def _load_ids(self) -> set[str]:
        if not self.path.exists():
            return set()
        ids: set[str] = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(item, dict) and item.get("h2h_snapshot_id"):
                ids.add(str(item["h2h_snapshot_id"]))
        return ids

    def append(self, snapshot: dict[str, Any]) -> str | None:
        sid = str(snapshot["h2h_snapshot_id"])
        if sid in self._ids:
            return None
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
        self._ids.add(sid)
        return sid


class H2HOutcomeStore:
    """Append-only final-outcome join for immutable H2H snapshots."""

    def __init__(self, root: Path):
        self.path = root / OUTCOME_FILE
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ids = self._load_ids()

    def _load_ids(self) -> set[str]:
        if not self.path.exists():
            return set()
        ids: set[str] = set()
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(item, dict) and item.get("h2h_snapshot_id"):
                ids.add(str(item["h2h_snapshot_id"]))
        return ids

    def append(self, *, snapshot_id: str, fixture_id: int, home_goals: int, away_goals: int, captured_at: datetime) -> bool:
        if snapshot_id in self._ids:
            return False
        result = "1" if home_goals > away_goals else "2" if home_goals < away_goals else "X"
        item = {
            "schema_version": SCHEMA_VERSION,
            "h2h_snapshot_id": snapshot_id,
            "fixture_id": int(fixture_id),
            "final_home_goals": int(home_goals),
            "final_away_goals": int(away_goals),
            "final_total_goals": int(home_goals + away_goals),
            "final_result_1x2": result,
            "captured_at": captured_at.astimezone(UTC).isoformat(),
            "source": "prediction_ledger.settlement",
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
            handle.flush()
        self._ids.add(snapshot_id)
        return True
