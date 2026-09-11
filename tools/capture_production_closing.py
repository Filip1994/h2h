from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from quantbot.api import APIError, APIFootballClient
from quantbot.config import Settings
from quantbot.markets import extract_best_quotes
from quantbot.persistence import OddsSnapshotStore
from quantbot.storage import BetStore
from quantbot.types import Market

MIN_SECONDS = 10 * 60
MAX_SECONDS = 20 * 60


def main() -> int:
    settings = Settings.from_env(ROOT)
    now = datetime.now(UTC)
    bets = BetStore(settings.bets_file).load()
    store = OddsSnapshotStore(ROOT / "data" / "odds_snapshots.jsonl")
    api = APIFootballClient(settings)
    captured = 0
    attempted = 0
    unavailable = 0

    for bet in bets:
        if str(bet.get("status", "")).upper() != "PENDING":
            continue
        try:
            kickoff = datetime.fromisoformat(str(bet["kickoff"])).astimezone(UTC)
            fixture_id = int(bet["event_id"])
            bookmaker_id = int(bet["bookmaker_id"])
            market = Market.parse(str(bet["market"]))
        except (KeyError, TypeError, ValueError):
            continue

        seconds_to_kickoff = (kickoff - now).total_seconds()
        if not MIN_SECONDS <= seconds_to_kickoff <= MAX_SECONDS:
            continue
        attempted += 1

        try:
            raw = api.odds(fixture_id)
        except APIError as exc:
            unavailable += 1
            print(f"T15_UNAVAILABLE fixture={fixture_id} reason=API_ERROR:{exc}")
            continue

        quotes = extract_best_quotes(
            raw,
            bookmaker_priority=(bookmaker_id,),
            allow_any_bookmaker=False,
            captured_at=now,
            only_bookmaker_id=bookmaker_id,
        )
        quote = quotes.get(market)
        if quote is None or not 0.0 <= quote.overround <= settings.max_market_overround:
            unavailable += 1
            print(
                f"T15_UNAVAILABLE fixture={fixture_id} bookmaker={bookmaker_id} "
                f"market={market.value}"
            )
            continue

        snapshot_id = store.append_quote(
            quote,
            fixture_id=fixture_id,
            snapshot_type="CLOSING",
            prediction_id=str(bet.get("prediction_id") or "") or None,
            bet_id=str(bet.get("id") or "") or None,
            signal_id=str(bet.get("signal_id") or "") or None,
            captured_by="production-closing-t15",
            source_endpoint="odds",
            source_params={"fixture": fixture_id},
        )
        if snapshot_id:
            bet["closing_odd"] = round(quote.odd, 4)
            bet["closing_opposite_odd"] = round(quote.opposite_odd, 4)
            bet["closing_market_probability_devig"] = round(quote.devig_probability, 6)
            bet["closing_odds_captured_at"] = now.isoformat()
            bet["closing_5m_odd"] = round(quote.odd, 4)
            bet["closing_5m_opposite_odd"] = round(quote.opposite_odd, 4)
            bet["closing_5m_market_probability_devig"] = round(quote.devig_probability, 6)
            bet["closing_5m_odds_captured_at"] = now.isoformat()
            bet["closing_snapshot_id"] = snapshot_id
            bet["closing_capture_target"] = "T-15m"
            bet["closing_capture_window"] = "T-10m_to_T-20m"
            captured += 1
            print(
                f"T15_CAPTURED fixture={fixture_id} bookmaker={bookmaker_id} "
                f"market={market.value} odd={quote.odd} captured_at={now.isoformat()}"
            )

    if captured:
        BetStore(settings.bets_file).save(bets)

    print(json.dumps({
        "target": "T-15m",
        "window": "T-10m_to_T-20m",
        "attempted": attempted,
        "captured": captured,
        "unavailable": unavailable,
        "timestamp": now.isoformat(),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
