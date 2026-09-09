from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from .api import APIBudgetExceeded, APIError, APIFootballClient
from .config import Settings
from .filters import is_allowed_match
from .markets import extract_all_valid_quotes
from .odds_lifecycle import lifecycle_contract, observations_for
from .parsing import current_fixture_fields
from .persistence import OddsSnapshotStore
from .storage import atomic_write_json

STATE_SCHEMA_VERSION = 1
BUDGET_SCHEMA_VERSION = 1
COVERAGE_SCHEMA_VERSION = 1
SUPPORTED_STATUSES = {"NS", "TBD"}
DISCOVERY_DAYS = 3


def _parse(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def cadence_minutes(hours_to_kickoff: float) -> int:
    if hours_to_kickoff > 72:
        return 24 * 60
    if hours_to_kickoff > 48:
        return 24 * 60
    if hours_to_kickoff > 24:
        return 8 * 60
    if hours_to_kickoff > 6:
        return 2 * 60
    if hours_to_kickoff > 3:
        return 30
    if hours_to_kickoff > 1:
        return 15
    return 5


def target_next_due(now: datetime, kickoff: datetime) -> datetime:
    hours = (kickoff - now).total_seconds() / 3600.0
    return now + timedelta(minutes=cadence_minutes(hours))


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return default


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
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


def _append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _budget_path(settings: Settings) -> Path:
    return settings.root / "odds_collection_budget.json"


def _state_path(settings: Settings) -> Path:
    return settings.root / "odds_collection_state.json"


def _coverage_path(settings: Settings) -> Path:
    return settings.root / "data" / "odds_collection_coverage.jsonl"


def _metrics_path(settings: Settings) -> Path:
    return settings.root / "odds_collection_metrics.json"


def _load_budget(settings: Settings, day: date) -> dict[str, Any]:
    value = _load_json(_budget_path(settings), {})
    if not isinstance(value, dict) or value.get("date") != day.isoformat():
        return {
            "schema_version": BUDGET_SCHEMA_VERSION,
            "date": day.isoformat(),
            "request_budget": settings.api_request_budget,
            "reserve": settings.api_budget_reserve,
            "working_budget": settings.api_request_budget - settings.api_budget_reserve,
            "requests_used": 0,
        }
    return value


def _load_state(settings: Settings) -> dict[str, Any]:
    value = _load_json(_state_path(settings), {})
    if not isinstance(value, dict):
        value = {}
    value.setdefault("schema_version", STATE_SCHEMA_VERSION)
    value.setdefault("fixtures", {})
    return value


def _state_entry(
    state: dict[str, Any], fields: dict[str, Any], now: datetime
) -> dict[str, Any]:
    key = str(fields["fixture_id"])
    fixtures = state["fixtures"]
    item = fixtures.get(key)
    if not isinstance(item, dict):
        item = {
            "fixture_id": fields["fixture_id"],
            "first_discovered_at": now.isoformat(),
            "query_count": 0,
            "observations": 0,
        }
        fixtures[key] = item
    item.update(
        {
            "kickoff": fields["kickoff"].isoformat(),
            "league_id": fields["league_id"],
            "league": fields["league_name"],
            "country": fields["country"],
            "home": fields["home_name"],
            "away": fields["away_name"],
            "last_seen_at": now.isoformat(),
        }
    )
    return item


def _record_outcome(
    coverage_path: Path,
    *,
    now: datetime,
    fields: dict[str, Any],
    outcome: str,
    reason: str | None = None,
    observations: int = 0,
    next_due_at: datetime | None = None,
) -> None:
    _append_jsonl(
        coverage_path,
        [
            {
                "schema_version": COVERAGE_SCHEMA_VERSION,
                "captured_at": now.isoformat(),
                "fixture_id": fields["fixture_id"],
                "kickoff": fields["kickoff"].isoformat(),
                "league_id": fields["league_id"],
                "league": fields["league_name"],
                "country": fields["country"],
                "home": fields["home_name"],
                "away": fields["away_name"],
                "outcome": outcome,
                "reason": reason,
                "observations": observations,
                "next_due_at": next_due_at.isoformat() if next_due_at else None,
            }
        ],
    )


def _bucket(hours_to_kickoff: float) -> str:
    if hours_to_kickoff > 72:
        return ">72h"
    if hours_to_kickoff > 48:
        return "72-48h"
    if hours_to_kickoff > 24:
        return "48-24h"
    if hours_to_kickoff > 12:
        return "24-12h"
    if hours_to_kickoff > 6:
        return "12-6h"
    if hours_to_kickoff > 3:
        return "6-3h"
    if hours_to_kickoff > 1:
        return "3-1h"
    if hours_to_kickoff > 1 / 6:
        return "60-10m"
    return "<=10m"


def _lifecycle_metrics(settings: Settings, day: date) -> dict[str, Any]:
    path = settings.root / "data" / "odds_snapshots.jsonl"
    rows = _load_jsonl(path)
    by_key: dict[tuple[int, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        captured = _parse(row.get("odds_captured_at"))
        if captured is None:
            continue
        kickoff = _parse(row.get("kickoff"))
        if kickoff is not None and kickoff.astimezone(settings.timezone).date() != day:
            continue
        try:
            key = (int(row["fixture_id"]), str(row["market"]), int(row["bookmaker_id"]))
        except (KeyError, TypeError, ValueError):
            continue
        by_key[key].append(row)
    opening = 0
    closing = 0
    entry = 0
    for key, observations in by_key.items():
        observations.sort(
            key=lambda row: (
                _parse(row.get("odds_captured_at")) or datetime.min.replace(tzinfo=UTC)
            )
        )
        first = observations[0] if observations else None
        if first:
            opening += 1
        if any(str(row.get("snapshot_type")) == "ENTRY" for row in observations):
            entry += 1
        if any(
            str(row.get("snapshot_type")) in {"T5", "CLOSING"} for row in observations
        ):
            closing += 1
    return {
        "lifecycle_keys": len(by_key),
        "opening_coverage_pct": round(opening / max(1, len(by_key)), 6),
        "entry_coverage_pct": round(entry / max(1, len(by_key)), 6),
        "closing_coverage_pct": round(closing / max(1, len(by_key)), 6),
    }


def _production_signal_coverage(settings: Settings, day: date) -> dict[str, Any]:
    bets = _load_json(settings.bets_file, [])
    alerts = _load_json(settings.root / "intraday_alerts.json", [])
    result: dict[str, Any] = {}
    for name, rows in (("production", bets), ("strong_signal", alerts)):
        selected = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            kickoff = _parse(row.get("kickoff"))
            if kickoff and kickoff.astimezone(settings.timezone).date() == day:
                selected.append(row)
        full = 0
        partial = 0
        for row in selected:
            try:
                fixture_id = int(row["event_id"])
                market = str(row["market"])
                bookmaker_id = int(row["bookmaker_id"])
                pick_at = _parse(row.get("odds_captured_at"))
                kickoff = _parse(row.get("kickoff"))
            except (KeyError, TypeError, ValueError):
                partial += 1
                continue
            if pick_at is None or kickoff is None:
                partial += 1
                continue
            contract = lifecycle_contract(
                observations_for(
                    settings.root / "data" / "odds_snapshots.jsonl",
                    fixture_id=fixture_id,
                    market=market,
                    bookmaker_id=bookmaker_id,
                ),
                pick_at=pick_at,
                kickoff=kickoff,
            )
            if contract["coverage"] == "FULLY_AUDITABLE":
                full += 1
            else:
                partial += 1
        result[f"{name}_records"] = len(selected)
        result[f"{name}_full_lifecycle"] = full
        result[f"{name}_partial_lifecycle"] = partial
    return result


def collect(settings: Settings, now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now(UTC)).astimezone(UTC)
    state = _load_state(settings)
    budget = _load_budget(settings, now.astimezone(settings.timezone).date())
    remaining = max(
        0, int(budget["working_budget"]) - int(budget.get("requests_used") or 0)
    )
    api: APIFootballClient | None = None
    if remaining > 0:
        run_settings = replace(
            settings,
            api_request_budget=remaining + settings.api_budget_reserve,
            api_budget_reserve=settings.api_budget_reserve,
        )
        api = APIFootballClient(run_settings)
    else:
        api = APIFootballClient(settings)

    eligible: dict[int, dict[str, Any]] = {}
    fixture_results = Counter()
    observations_captured = 0
    scanned_buckets = Counter()
    scanned_at: list[str] = []
    coverage_path = _coverage_path(settings)
    snapshot_store = OddsSnapshotStore(settings.root / "data" / "odds_snapshots.jsonl")
    existing_snapshot_rows = _load_jsonl(
        settings.root / "data" / "odds_snapshots.jsonl"
    )
    existing_keys = {
        (int(row["fixture_id"]), str(row["market"]), int(row["bookmaker_id"]))
        for row in existing_snapshot_rows
        if all(key in row for key in ("fixture_id", "market", "bookmaker_id"))
    }

    for offset in range(DISCOVERY_DAYS + 1):
        target = now.astimezone(settings.timezone).date() + timedelta(days=offset)
        try:
            raw_fixtures = api.fixtures_by_date(target.isoformat())
        except APIBudgetExceeded:
            break
        except APIError:
            continue
        for raw in raw_fixtures:
            try:
                fields = current_fixture_fields(raw)
            except (TypeError, ValueError):
                continue
            kickoff = fields["kickoff"]
            if fields["status"] not in SUPPORTED_STATUSES:
                continue
            hours = (kickoff - now).total_seconds() / 3600.0
            if hours <= 0 or hours > 72.0 + (5.0 / 60.0):
                continue
            if not is_allowed_match(
                fields["country"],
                fields["league_name"],
                fields["home_name"],
                fields["away_name"],
                settings.excluded_countries,
            ):
                continue
            eligible[int(fields["fixture_id"])] = fields
            item = _state_entry(state, fields, now)
            next_due = _parse(item.get("next_due_at"))
            if next_due is None:
                next_due = now
            if next_due > now:
                fixture_results["NOT_DUE"] += 1
                continue
            if remaining <= api.request_count:
                fixture_results["BUDGET_EXHAUSTED"] += 1
                _record_outcome(
                    coverage_path,
                    now=now,
                    fields=fields,
                    outcome="BUDGET_EXHAUSTED",
                    reason="DAILY_WORKING_BUDGET_EXHAUSTED",
                    next_due_at=now + timedelta(minutes=5),
                )
                continue
            try:
                raw_odds = api.odds(int(fields["fixture_id"]))
                item["query_count"] = int(item.get("query_count") or 0) + 1
                item["last_queried_at"] = now.isoformat()
                item["last_query_ttk_hours"] = round(hours, 6)
                item["last_query_bucket"] = _bucket(hours)
                scanned_buckets[_bucket(hours)] += 1
                scanned_at.append(now.isoformat())
                if not raw_odds:
                    fixture_results["NO_ODDS_RESPONSE"] += 1
                    item["last_outcome"] = "NO_ODDS_RESPONSE"
                    _record_outcome(
                        coverage_path,
                        now=now,
                        fields=fields,
                        outcome="NO_ODDS_RESPONSE",
                        next_due_at=target_next_due(now, kickoff),
                    )
                else:
                    quotes = extract_all_valid_quotes(raw_odds, captured_at=now)
                    if not quotes:
                        fixture_results["INVALID_RESPONSE"] += 1
                        item["last_outcome"] = "INVALID_RESPONSE"
                        _record_outcome(
                            coverage_path,
                            now=now,
                            fields=fields,
                            outcome="INVALID_RESPONSE",
                            reason="NO_SUPPORTED_VALID_QUOTES",
                            next_due_at=target_next_due(now, kickoff),
                        )
                    else:
                        added = 0
                        seconds_to_kickoff = (kickoff - now).total_seconds()
                        snapshot_type = (
                            "T5" if 120 <= seconds_to_kickoff <= 480 else "INTERMEDIATE"
                        )
                        for quote in quotes:
                            key = (
                                int(fields["fixture_id"]),
                                quote.market.value,
                                quote.bookmaker_id,
                            )
                            lifecycle_type = (
                                "OPENING" if key not in existing_keys else snapshot_type
                            )
                            snapshot_id = snapshot_store.append_quote(
                                quote,
                                fixture_id=int(fields["fixture_id"]),
                                snapshot_type=lifecycle_type,
                                captured_by="exhaustive_odds_collector",
                                source_params={"fixture": int(fields["fixture_id"])},
                            )
                            if snapshot_id:
                                existing_keys.add(key)
                                added += 1
                        observations_captured += added
                        fixture_results["QUERIED"] += 1
                        item["last_outcome"] = "QUERIED"
                        item["observations"] = (
                            int(item.get("observations") or 0) + added
                        )
                        item["opening_observed"] = any(
                            (
                                int(fields["fixture_id"]),
                                quote.market.value,
                                quote.bookmaker_id,
                            )
                            not in existing_keys
                            for quote in quotes
                        ) or bool(item.get("opening_observed"))
                        _record_outcome(
                            coverage_path,
                            now=now,
                            fields=fields,
                            outcome="QUERIED",
                            observations=added,
                            next_due_at=target_next_due(now, kickoff),
                        )
                item["next_due_at"] = target_next_due(now, kickoff).isoformat()
            except APIBudgetExceeded:
                fixture_results["BUDGET_EXHAUSTED"] += 1
                item["last_outcome"] = "BUDGET_EXHAUSTED"
                item["next_due_at"] = (now + timedelta(minutes=5)).isoformat()
                _record_outcome(
                    coverage_path,
                    now=now,
                    fields=fields,
                    outcome="BUDGET_EXHAUSTED",
                    reason="API_CLIENT_BUDGET_EXHAUSTED",
                    next_due_at=now + timedelta(minutes=5),
                )
            except APIError as exc:
                fixture_results["API_ERROR"] += 1
                item["last_outcome"] = "API_ERROR"
                item["last_error"] = str(exc)[:500]
                item["next_due_at"] = (now + timedelta(minutes=5)).isoformat()
                _record_outcome(
                    coverage_path,
                    now=now,
                    fields=fields,
                    outcome="API_ERROR",
                    reason=str(exc)[:500],
                    next_due_at=now + timedelta(minutes=5),
                )

    budget["requests_used"] = int(budget.get("requests_used") or 0) + api.request_count
    budget["last_run_at"] = now.isoformat()
    budget["last_run_requests"] = api.request_count
    atomic_write_json(_budget_path(settings), budget)
    state["updated_at"] = now.isoformat()
    state["last_run_requests"] = api.request_count
    state["last_run_outcomes"] = dict(fixture_results)
    atomic_write_json(_state_path(settings), state)

    lifecycle = _lifecycle_metrics(settings, now.astimezone(settings.timezone).date())
    signal = _production_signal_coverage(
        settings, now.astimezone(settings.timezone).date()
    )
    queried = int(fixture_results["QUERIED"])
    no_odds = int(fixture_results["NO_ODDS_RESPONSE"])
    invalid = int(fixture_results["INVALID_RESPONSE"])
    errors = int(fixture_results["API_ERROR"])
    budget_exhausted = int(fixture_results["BUDGET_EXHAUSTED"])
    metrics = {
        "schema_version": 1,
        "timestamp": now.isoformat(),
        "date": now.astimezone(settings.timezone).date().isoformat(),
        "eligible_fixtures": len(eligible),
        "queried_fixtures": queried,
        "odds_query_coverage_pct": round(queried / max(1, len(eligible)), 6),
        "successful_responses": queried,
        "empty_responses": no_odds,
        "invalid_responses": invalid,
        "api_errors": errors,
        "budget_exhausted": budget_exhausted,
        "api_requests_used_this_run": api.request_count,
        "daily_working_budget": budget["working_budget"],
        "daily_budget_used": budget["requests_used"],
        "daily_budget_remaining": max(
            0, budget["working_budget"] - budget["requests_used"]
        ),
        "observations_captured": observations_captured,
        "observations_per_fixture": round(observations_captured / max(1, queried), 4),
        "provider_availability_by_ttk": dict(sorted(scanned_buckets.items())),
        "actual_scan_timestamps": scanned_at[-100:],
        **lifecycle,
        **signal,
        "degraded": bool(
            len(eligible) > 0 and (queried / max(1, len(eligible))) < 0.80
        ),
        "degraded_reasons": [
            reason
            for reason, condition in (
                (
                    "LOW_ODDS_QUERY_COVERAGE",
                    len(eligible) > 0 and queried / max(1, len(eligible)) < 0.80,
                ),
                ("BUDGET_EXHAUSTED", budget_exhausted > 0),
                ("API_ERRORS", errors > 0),
            )
            if condition
        ],
    }
    atomic_write_json(_metrics_path(settings), metrics)
    return metrics
