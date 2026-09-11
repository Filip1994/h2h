from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .bookmaker_registry import bookmaker_identity
from .observation_identity import canonical_observation_id
from .types import OddsQuote

SNAPSHOT_SCHEMA_VERSION = 3
SNAPSHOT_TYPES = {"OPENING", "ENTRY", "INTERMEDIATE", "T5", "CLOSING"}


def source_request_hash(endpoint: str, params: dict[str, Any]) -> str:
    canonical = json.dumps(
        [endpoint, sorted(params.items())], ensure_ascii=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def snapshot_id(record: dict[str, Any]) -> str:
    """Immutable identity for one persisted observation record.

    Unlike observation_id, this identity includes temporal/provenance fields so
    two observations of the same quote state remain distinct immutable records.
    """
    canonical = {
        key: record.get(key)
        for key in (
            "fixture_id",
            "market",
            "bookmaker_id",
            "selection",
            "odd",
            "opposite_odd",
            "odds_captured_at",
            "snapshot_type",
            "source_request_hash",
            "observation_id",
        )
    }
    return hashlib.sha256(
        json.dumps(
            canonical, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _derive_observation_id(record: dict[str, Any]) -> str | None:
    try:
        return canonical_observation_id(
            fixture_id=int(record["fixture_id"]),
            market=str(record["market"]),
            bookmaker_id=int(record["bookmaker_id"]),
            selection=str(record.get("selection") or record["market"]),
            odd=float(record["odd"]),
            opposite_odd=float(record["opposite_odd"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


class OddsSnapshotStore:
    """Append-only canonical odds snapshot store; existing records are immutable."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ids = self._load_ids()

    def _load_ids(self) -> set[str]:
        if not self.path.exists():
            return set()
        ids: set[str] = set()
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if isinstance(item, dict) and item.get("snapshot_id"):
                    ids.add(str(item["snapshot_id"]))
        return ids

    def load(self) -> list[dict[str, Any]]:
        """Load persisted snapshots without mutating the append-only store.

        Legacy schema-v2 rows are enriched in memory with the v3 observation_id;
        the original persisted bytes remain immutable.
        """
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except (TypeError, ValueError, json.JSONDecodeError):
                    continue
                if isinstance(item, dict):
                    if not item.get("observation_id"):
                        derived = _derive_observation_id(item)
                        if derived:
                            item = dict(item)
                            item["observation_id"] = derived
                            item["observation_identity_version"] = 1
                    records.append(item)
        return records

    def append(self, record: dict[str, Any]) -> str | None:
        snapshot_type = str(record.get("snapshot_type") or "")
        if snapshot_type not in SNAPSHOT_TYPES:
            raise ValueError(f"Nepoznat snapshot_type: {snapshot_type}")
        item = dict(record)
        item["schema_version"] = SNAPSHOT_SCHEMA_VERSION
        identity = bookmaker_identity(item.get("bookmaker_id"), item.get("bookmaker"))
        item["bookmaker"] = identity["bookmaker"]
        item["bookmaker_logo_url"] = identity["logo_url"]
        item["bookmaker_logo_source"] = identity["logo_source"]
        item["bookmaker_logo_verified"] = identity["logo_verified"]
        item["observation_id"] = canonical_observation_id(
            fixture_id=int(item["fixture_id"]),
            market=str(item["market"]),
            bookmaker_id=int(item["bookmaker_id"]),
            selection=str(item.get("selection") or item["market"]),
            odd=float(item["odd"]),
            opposite_odd=float(item["opposite_odd"]),
        )
        item["observation_identity_version"] = 1
        item["snapshot_id"] = snapshot_id(item)
        if item["snapshot_id"] in self._ids:
            return None
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                )
                + "\n"
            )
            handle.flush()
        self._ids.add(item["snapshot_id"])
        return str(item["snapshot_id"])

    def append_quote(
        self,
        quote: OddsQuote,
        *,
        fixture_id: int,
        snapshot_type: str,
        prediction_id: str | None = None,
        bet_id: str | None = None,
        signal_id: str | None = None,
        captured_by: str = "UNKNOWN",
        source_endpoint: str = "odds",
        source_params: dict[str, Any] | None = None,
        kickoff: datetime | None = None,
        league_id: int | None = None,
        league: str | None = None,
    ) -> str | None:
        params = source_params or {"fixture": fixture_id}
        return self.append(
            {
                "fixture_id": fixture_id,
                "league_id": league_id,
                "league": league,
                "kickoff": kickoff.astimezone(UTC).isoformat() if kickoff else None,
                "market": quote.market.value,
                "bookmaker_id": quote.bookmaker_id,
                "bookmaker": quote.bookmaker_name,
                "selection": quote.market.value,
                "odd": round(quote.odd, 4),
                "opposite_odd": round(quote.opposite_odd, 4),
                "devig_probability": round(quote.devig_probability, 6),
                "overround": round(quote.overround, 6),
                "odds_captured_at": quote.captured_at.astimezone(UTC).isoformat(),
                "snapshot_type": snapshot_type,
                "prediction_id": prediction_id,
                "bet_id": bet_id,
                "signal_id": signal_id or prediction_id,
                "source_endpoint": source_endpoint,
                "source_request_hash": source_request_hash(source_endpoint, params),
                "captured_by": captured_by,
                "schema_version": SNAPSHOT_SCHEMA_VERSION,
            }
        )


def record_prediction_quote(
    settings: Any,
    prediction: dict[str, Any],
    *,
    snapshot_type: str = "ENTRY",
    bet_id: str | None = None,
    captured_by: str = "generate",
    store: OddsSnapshotStore | None = None,
) -> str | None:
    required = (
        prediction.get("odd"),
        prediction.get("opposite_odd"),
        prediction.get("bookmaker_id"),
        prediction.get("odds_captured_at"),
    )
    if any(value is None for value in required):
        return None

    from .types import Market

    quote = OddsQuote(
        market=Market.parse(str(prediction["market"])),
        odd=float(prediction["odd"]),
        opposite_odd=float(prediction["opposite_odd"]),
        bookmaker_id=int(prediction["bookmaker_id"]),
        bookmaker_name=str(prediction.get("bookmaker") or prediction["bookmaker_id"]),
        captured_at=datetime.fromisoformat(
            str(prediction["odds_captured_at"])
        ).astimezone(UTC),
    )
    target = store or OddsSnapshotStore(settings.root / "data" / "odds_snapshots.jsonl")
    return target.append_quote(
        quote,
        fixture_id=int(prediction["event_id"]),
        snapshot_type=snapshot_type,
        prediction_id=str(prediction.get("id") or "") or None,
        bet_id=bet_id,
        signal_id=str(prediction.get("signal_id") or prediction.get("id") or "")
        or None,
        captured_by=captured_by,
        source_params={"fixture": int(prediction["event_id"])},
        kickoff=datetime.fromisoformat(str(prediction["kickoff"])).astimezone(UTC)
        if prediction.get("kickoff")
        else None,
        league_id=int(prediction["league_id"]) if prediction.get("league_id") else None,
        league=str(prediction["league"]) if prediction.get("league") else None,
    )
