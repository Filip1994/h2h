from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BETS = ROOT / "bets.json"
SNAPSHOTS = ROOT / "data" / "odds_snapshots.jsonl"
OUT = ROOT / "production_dashboard.json"


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        value = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except (TypeError, ValueError):
        return None


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return default


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return rows


def key(row: dict[str, Any]) -> tuple[int, str, int] | None:
    try:
        return int(row["fixture_id"]), str(row["market"]), int(row["bookmaker_id"])
    except (KeyError, TypeError, ValueError):
        return None


def first_observation(rows: list[dict[str, Any]], pick_at: datetime | None) -> dict[str, Any] | None:
    candidates = [r for r in rows if parse_dt(r.get("odds_captured_at")) is not None]
    if pick_at is not None:
        candidates = [r for r in candidates if parse_dt(r.get("odds_captured_at")) <= pick_at]
    return candidates[0] if candidates else None


def latest_observation(rows: list[dict[str, Any]], now: datetime) -> dict[str, Any] | None:
    candidates = [r for r in rows if (ts := parse_dt(r.get("odds_captured_at"))) is not None and ts <= now]
    return candidates[-1] if candidates else None


def closing_observation(rows: list[dict[str, Any]], kickoff: datetime | None) -> dict[str, Any] | None:
    if kickoff is None:
        return None
    candidates: list[dict[str, Any]] = []
    for row in rows:
        ts = parse_dt(row.get("odds_captured_at"))
        if ts is None or ts > kickoff:
            continue
        seconds = (kickoff - ts).total_seconds()
        if 120 <= seconds <= 480:
            candidates.append(row)
    return candidates[-1] if candidates else None


def compact_observation(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "observation_id": row.get("observation_id"),
        "odd": row.get("odd"),
        "opposite_odd": row.get("opposite_odd"),
        "captured_at": row.get("odds_captured_at"),
        "snapshot_type": row.get("snapshot_type"),
        "bookmaker_id": row.get("bookmaker_id"),
        "bookmaker": row.get("bookmaker"),
    }


def enrich(bet: dict[str, Any], grouped: dict[tuple[int, str, int], list[dict[str, Any]]], now: datetime) -> dict[str, Any]:
    try:
        k = (int(bet["event_id"]), str(bet["market"]), int(bet["bookmaker_id"]))
    except (KeyError, TypeError, ValueError):
        k = None
    rows = grouped.get(k, []) if k else []
    pick_at = parse_dt(bet.get("odds_captured_at") or bet.get("created_at"))
    kickoff = parse_dt(bet.get("kickoff"))
    opening = first_observation(rows, pick_at)
    live = latest_observation(rows, now)
    closing = closing_observation(rows, kickoff)
    live_ts = parse_dt(live.get("odds_captured_at")) if live else None
    if live_ts is None:
        live_state = "NO_OBSERVATION"
    else:
        age_minutes = max(0.0, (now - live_ts).total_seconds() / 60.0)
        live_state = "FRESH" if age_minutes <= 15 else "STALE"
    closing_odd = closing.get("odd") if closing else None
    pick_odd = bet.get("odd")
    clv = None
    try:
        if float(pick_odd) > 1.0 and float(closing_odd) > 1.0:
            clv = round(float(pick_odd) / float(closing_odd) - 1.0, 6)
    except (TypeError, ValueError):
        pass
    item = dict(bet)
    item["production_lifecycle"] = {
        "opening": compact_observation(opening),
        "pick": {
            "odd": bet.get("odd"),
            "captured_at": bet.get("odds_captured_at"),
            "observation_id": bet.get("pick_observation_id"),
        },
        "live": compact_observation(live),
        "live_state": live_state,
        "closing": compact_observation(closing),
        "closing_rule": "T-2m_to_T-8m_exact_pre_kickoff_observation",
        "clv_odds_pct": clv,
        "coverage": "FULL" if opening and live and closing else "PARTIAL",
    }
    return item


def main() -> int:
    now = datetime.now(UTC)
    bets = load_json(BETS, [])
    if not isinstance(bets, list):
        bets = []
    snapshots = load_jsonl(SNAPSHOTS)
    grouped: dict[tuple[int, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in snapshots:
        k = key(row)
        ts = parse_dt(row.get("odds_captured_at"))
        if k and ts:
            grouped[k].append(row)
    for rows in grouped.values():
        rows.sort(key=lambda r: parse_dt(r.get("odds_captured_at")) or datetime.min.replace(tzinfo=UTC))

    production = [b for b in bets if str(b.get("signal_source", "DAILY_BULLETIN")).upper() != "INTRADAY_ALERT"]
    enriched = [enrich(b, grouped, now) for b in production if isinstance(b, dict)]
    active = [b for b in enriched if str(b.get("status", "PENDING")).upper() == "PENDING"]
    history = [b for b in enriched if str(b.get("status", "PENDING")).upper() != "PENDING"]
    meta = load_json(ROOT / "ledger_meta.json", {})
    output = {
        "schema_version": 1,
        "generated_at": now.isoformat(),
        "truth": "data/odds_snapshots.jsonl + bets.json",
        "rules": {
            "opening": "first persisted observation for the exact Production fixture/market/bookmaker at or before Pick",
            "live": "latest persisted observation for the exact Production fixture/market/bookmaker",
            "closing": "latest exact-bookmaker observation 2-8 minutes before kickoff; otherwise null",
            "clv": "Pick odd / Closing odd - 1; null when Closing is unavailable",
            "missing_data": "null; dashboard renders as —",
        },
        "initial_bank": meta.get("initial_bank", 50000),
        "active": active,
        "history": history,
        "counts": {"production": len(enriched), "active": len(active), "history": len(history), "snapshots": len(snapshots)},
    }
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output["counts"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
