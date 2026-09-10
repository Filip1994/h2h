from __future__

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quantbot.api import APIBudgetExceeded, APIError, APIFootballClient
from quantbot.config import Settings
from quantbot.markets import extract_best_quotes
from quantbot.storage import BetStore
from quantbot.types import Market

MAX_QUOTE_AGE_SECONDS = 30 * 60
MIN_LEAD_SECONDS = 300


def _load_json(path: Path, default: Any):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return default


def _load_run_result(path: Path) -> dict | None:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        candidate = line.strip()
        if not candidate.startswith("{"):
            continue
        try:
            value = json.loads(candidate)
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(value, dict):
            return value
    return None


def _parse(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _first_number(payload: dict, *keys: str) -> int | None:
    for key in keys:
        value = payload.get(key)
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            return None
    return None


def _production_quote_guard(settings: Settings, *, now: datetime, previous_health: dict) -> dict:
    """Keep every open Production pick on an exact-bookmaker quote <=30m old.

    This guard is independent of the six-hour Strong/Near lookahead. It warms
    every open Production pick before T-6h, so the T-6h cadence never starts
    from a quote that is many hours old.
    """
    bets = BetStore(settings.bets_file).load()
    predictions = _load_json(settings.predictions_file, [])
    if not isinstance(predictions, list):
        predictions = []
    pred_key = {
        (int(p["event_id"]), str(p["market"])): p
        for p in predictions
        if isinstance(p, dict) and p.get("event_id") is not None and p.get("market")
    }
    previous_guard = previous_health.get("production_quote_guard", {}) if isinstance(previous_health, dict) else {}
    picks = previous_guard.get("picks", {}) if isinstance(previous_guard, dict) else {}
    if not isinstance(picks, dict):
        picks = {}
    api = APIFootballClient(settings)
    active = []
    errors = []

    for bet in bets:
        if str(bet.get("status", "")).upper() not in {"PENDING", "OPEN", "ACTIVE"}:
            continue
        kickoff = _parse(bet.get("kickoff"))
        if kickoff is None or (kickoff - now).total_seconds() <= MIN_LEAD_SECONDS:
            continue
        if bet.get("event_id") is None or not bet.get("market") or bet.get("bookmaker_id") is None:
            continue
        fixture_id = int(bet["event_id"])
        market = Market.parse(str(bet["market"]))
        key = str(bet.get("id") or f"{fixture_id}_{market.value}")
        row = picks.setdefault(key, {})
        captured = _parse(row.get("quote_captured_at"))
        due = captured is None or (now - captured).total_seconds() >= MAX_QUOTE_AGE_SECONDS
        if due:
            try:
                raw = api.odds(fixture_id)
                quotes = extract_best_quotes(
                    raw,
                    bookmaker_priority=settings.bookmaker_priority,
                    allow_any_bookmaker=settings.allow_any_bookmaker,
                    captured_at=now,
                    only_bookmaker_id=int(bet["bookmaker_id"]),
                )
                quote = quotes.get(market)
                row.update({
                    "fixture_id": fixture_id,
                    "market": market.value,
                    "bookmaker_id": int(bet["bookmaker_id"]),
                    "bookmaker": bet.get("bookmaker"),
                    "kickoff": bet.get("kickoff"),
                    "prediction_id": pred_key.get((fixture_id, market.value), {}).get("id"),
                    "last_scan_at": now.isoformat(),
                })
                if quote is not None and 0.0 <= quote.overround <= settings.max_market_overround:
                    row.update({
                        "status": "FRESH",
                        "odd": round(float(quote.odd), 4),
                        "opposite_odd": round(float(quote.opposite_odd), 4),
                        "market_probability_devig": round(float(quote.devig_probability), 6),
                        "overround": round(float(quote.overround), 6),
                        "quote_captured_at": quote.captured_at.isoformat(),
                    })
                else:
                    row["status"] = "NO_VALID_CURRENT_QUOTE"
            except APIBudgetExceeded:
                row["status"] = "API_BUDGET_EXCEEDED"
                errors.append(f"{key}:API_BUDGET_EXCEEDED")
                break
            except APIError as exc:
                row["status"] = "API_ERROR"
                row["error"] = str(exc)
                errors.append(f"{key}:API_ERROR")

        captured = _parse(row.get("quote_captured_at"))
        age = (now - captured).total_seconds() if captured is not None else None
        if age is None or age > MAX_QUOTE_AGE_SECONDS:
            row["status"] = "STALE_QUOTE"
        elif row.get("status") in {"API_ERROR", "NO_VALID_CURRENT_QUOTE"}:
            row["status"] = "FRESH_FROM_LAST_VALID_OBSERVATION"
        row["quote_age_seconds"] = round(age, 1) if age is not None else None
        active.append({
            "id": key,
            "fixture_id": fixture_id,
            "market": market.value,
            "bookmaker_id": int(bet["bookmaker_id"]),
            "status": row.get("status"),
            "quote_age_seconds": row.get("quote_age_seconds"),
            "odd": row.get("odd"),
            "quote_captured_at": row.get("quote_captured_at"),
        })

    stale = [p for p in active if p["status"] == "STALE_QUOTE"]
    return {
        "schema_version": 1,
        "max_quote_age_seconds": MAX_QUOTE_AGE_SECONDS,
        "checked_at": now.isoformat(),
        "active_production_picks": len(active),
        "fresh_picks": len(active) - len(stale),
        "stale_picks": len(stale),
        "api_requests": api.request_count,
        "errors": errors,
        "picks": picks,
    }


def evaluate(run_result: dict, predictions: list[dict], *, now: datetime, lookahead_hours: float) -> dict:
    scanned = _first_number(run_result, "fixtures_scanned", "scanned")
    api_requests = _first_number(run_result, "api_requests", "request_count")
    if api_requests is None and isinstance(run_result.get("api_usage"), dict):
        api_requests = _first_number(run_result["api_usage"], "request_count", "requests")
    eligible: set[int] = set()
    for prediction in predictions:
        try:
            fixture_id = int(prediction["event_id"])
            kickoff = _parse(prediction["kickoff"])
        except (KeyError, TypeError, ValueError):
            continue
        if kickoff is None:
            continue
        seconds = (kickoff - now.astimezone(UTC)).total_seconds()
        if 300 < seconds <= lookahead_hours * 3600:
            eligible.add(fixture_id)
    errors: list[str] = []
    if scanned is None:
        errors.append("WATCHLIST_RESULT_MISSING_FIXTURE_SCAN_COUNT")
    if api_requests is None:
        errors.append("WATCHLIST_RESULT_MISSING_API_REQUEST_COUNT")
    if scanned is not None and eligible and scanned == 0:
        errors.append("ELIGIBLE_FIXTURES_WITH_ZERO_SCANS")
    if api_requests is not None and eligible and api_requests == 0:
        errors.append("ELIGIBLE_FIXTURES_WITH_ZERO_API_REQUESTS")
    if scanned is not None and scanned > 0 and api_requests == 0:
        errors.append("SCANS_REPORTED_WITH_ZERO_API_REQUESTS")
    if errors:
        status = "ERROR"
    elif not eligible:
        status = "NO_ELIGIBLE_FIXTURES"
    else:
        status = "OK"
    return {"schema_version": 1, "status": status, "checked_at": now.astimezone(UTC).isoformat(), "workflow_run_id": os.getenv("GITHUB_RUN_ID"), "source_sha": os.getenv("GITHUB_SHA"), "eligible_fixture_count": len(eligible), "fixtures_scanned": scanned, "api_requests": api_requests, "errors": errors, "observation_only": True}


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed scheduled watchlist and Production quote runtime gate")
    parser.add_argument("--run-output", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, default=Path("predictions.json"))
    parser.add_argument("--output", type=Path, default=Path("watchlist_runtime_health.json"))
    parser.add_argument("--lookahead-hours", type=float, default=float(os.getenv("INTRADAY_LOOKAHEAD_HOURS", "6")))
    args = parser.parse_args()
    run_result = _load_run_result(args.run_output)
    predictions = _load_json(args.predictions, [])
    now = datetime.now(UTC)
    previous_health = _load_json(args.output, {})
    if not isinstance(run_result, dict):
        payload = {"schema_version": 1, "status": "ERROR", "checked_at": now.isoformat(), "errors": ["WATCHLIST_RESULT_NOT_VALID_JSON_OBJECT"], "observation_only": True}
        args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return 1
    if not isinstance(predictions, list):
        predictions = []
    payload = evaluate(run_result, [item for item in predictions if isinstance(item, dict)], now=now, lookahead_hours=args.lookahead_hours)
    payload["production_quote_guard"] = _production_quote_guard(Settings.from_env(), now=now, previous_health=previous_health)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 1 if payload["status"] == "ERROR" else 0


if __name__ == "__main__":
    raise SystemExit(main())
