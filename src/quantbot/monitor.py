from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from .api import APIError, APIFootballClient
from .config import Settings
from .markets import extract_best_quotes
from .parsing import parse_datetime
from .storage import BetStore, PredictionStore
from .types import Market

FINISHED_STATUSES = {"FT", "AET", "PEN"}
VOID_STATUSES = {"CANC", "ABD"}
REVIEW_STATUSES = {"AWD", "WO"}


def _same_fixture(item: dict[str, Any], fixture_id: int) -> bool:
    try:
        return int(item.get("event_id")) == fixture_id
    except (TypeError, ValueError):
        return False


def market_outcome(market: Market, home_goals: int, away_goals: int) -> bool:
    total = home_goals + away_goals
    if market == Market.OVER_25:
        return total >= 3
    if market == Market.UNDER_25:
        return total <= 2
    if market == Market.BTTS_YES:
        return home_goals >= 1 and away_goals >= 1
    raise ValueError(f"Nepoznat market: {market}")


def regulation_score(payload: dict[str, Any]) -> tuple[int, int] | None:
    fulltime = (payload.get("score") or {}).get("fulltime") or {}
    home, away = fulltime.get("home"), fulltime.get("away")
    if home is not None and away is not None:
        return int(home), int(away)
    status = ((payload.get("fixture") or {}).get("status") or {}).get("short")
    goals = payload.get("goals") or {}
    if (
        status == "FT"
        and goals.get("home") is not None
        and goals.get("away") is not None
    ):
        return int(goals["home"]), int(goals["away"])
    return None


class LedgerMonitor:
    def __init__(
        self,
        settings: Settings,
        api: APIFootballClient | None = None,
        bet_store: BetStore | None = None,
        prediction_store: PredictionStore | None = None,
    ) -> None:
        self.settings = settings
        self.api = api or APIFootballClient(settings)
        self.bet_store = bet_store or BetStore(settings.bets_file)
        self.prediction_store = prediction_store or PredictionStore(
            settings.predictions_file
        )

    def _capture_closing_quotes(
        self, bets: list[dict[str, Any]], now: datetime
    ) -> bool:
        changed = False
        for bet in bets:
            if str(bet.get("status", "")).upper() != "PENDING":
                continue
            try:
                kickoff = parse_datetime(str(bet["kickoff"]))
                market = Market.parse(str(bet["market"]))
                bookmaker_id = int(bet["bookmaker_id"])
            except (KeyError, TypeError, ValueError):
                continue
            if not now < kickoff <= now + timedelta(minutes=120):
                continue
            try:
                raw = self.api.odds(int(bet["event_id"]))
            except APIError as exc:
                print(f"⚠️ Closing odds {bet.get('id')}: {exc}")
                continue
            quotes = extract_best_quotes(
                raw,
                bookmaker_priority=(bookmaker_id,),
                allow_any_bookmaker=False,
                captured_at=now,
                only_bookmaker_id=bookmaker_id,
            )
            quote = quotes.get(market)
            if quote is None or not (
                0.0 <= quote.overround <= self.settings.max_market_overround
            ):
                continue
            bet["closing_odd"] = round(quote.odd, 4)
            bet["closing_opposite_odd"] = round(quote.opposite_odd, 4)
            bet["closing_market_probability_devig"] = round(quote.devig_probability, 6)
            bet["closing_odds_captured_at"] = now.isoformat()
            changed = True
        return changed

    def run(self, now: datetime | None = None) -> dict[str, int]:
        now = now.astimezone(UTC) if now else datetime.now(UTC)
        bets = self.bet_store.load()
        predictions = self.prediction_store.load()
        changed_bets = self._capture_closing_quotes(bets, now)
        changed_predictions = False

        fixture_ids: set[int] = set()
        for item in [*bets, *predictions]:
            if str(item.get("status", "")).upper() != "PENDING":
                continue
            try:
                fixture_id = int(item["event_id"])
            except (KeyError, TypeError, ValueError):
                continue
            kickoff_raw = item.get("kickoff")
            if not kickoff_raw:
                fixture_ids.add(fixture_id)  # Legacy ledger: API status decides.
                continue
            try:
                kickoff = parse_datetime(str(kickoff_raw))
            except ValueError:
                fixture_ids.add(fixture_id)
                continue
            if now >= kickoff + timedelta(minutes=90):
                fixture_ids.add(fixture_id)

        settled_bets = 0
        settled_predictions = 0
        for fixture_id in sorted(fixture_ids):
            try:
                response = self.api.fixture(fixture_id)
            except APIError as exc:
                print(f"⚠️ Settlement fixture {fixture_id}: {exc}")
                continue
            if not response:
                continue
            payload = response[0]
            status = str(
                ((payload.get("fixture") or {}).get("status") or {}).get("short") or ""
            )
            api_date = (payload.get("fixture") or {}).get("date")
            api_kickoff: str | None = None
            if api_date:
                try:
                    api_kickoff = parse_datetime(str(api_date)).isoformat()
                except ValueError:
                    api_kickoff = None
            if api_kickoff:
                for item in bets:
                    if _same_fixture(item, fixture_id) and (
                        not item.get("kickoff") or status in {"PST", "NS", "TBD"}
                    ):
                        item["kickoff"] = api_kickoff
                        changed_bets = True
                for item in predictions:
                    if _same_fixture(item, fixture_id) and (
                        not item.get("kickoff") or status in {"PST", "NS", "TBD"}
                    ):
                        item["kickoff"] = api_kickoff
                        changed_predictions = True
            score = regulation_score(payload) if status in FINISHED_STATUSES else None

            for bet in bets:
                if (
                    not _same_fixture(bet, fixture_id)
                    or str(bet.get("status", "")).upper() != "PENDING"
                ):
                    continue
                if status in VOID_STATUSES:
                    bet.update(
                        {
                            "status": "VOID",
                            "profit": 0.0,
                            "settled_at": now.isoformat(),
                            "result": status,
                        }
                    )
                    changed_bets = True
                    settled_bets += 1
                    continue
                if status in REVIEW_STATUSES:
                    bet.update(
                        {
                            "status": "REVIEW",
                            "profit": 0.0,
                            "settled_at": now.isoformat(),
                            "result": status,
                        }
                    )
                    changed_bets = True
                    settled_bets += 1
                    continue
                if status not in FINISHED_STATUSES:
                    continue
                if score is None:
                    bet.update(
                        {
                            "status": "REVIEW",
                            "profit": 0.0,
                            "settled_at": now.isoformat(),
                            "result": status,
                        }
                    )
                    changed_bets = True
                    settled_bets += 1
                    continue
                try:
                    won = market_outcome(Market.parse(str(bet["market"])), *score)
                except (KeyError, ValueError):
                    bet.update(
                        {
                            "status": "REVIEW",
                            "profit": 0.0,
                            "settled_at": now.isoformat(),
                            "result": f"{score[0]}:{score[1]}",
                        }
                    )
                    changed_bets = True
                    settled_bets += 1
                    continue
                stake, odd = (
                    float(bet.get("stake") or 0.0),
                    float(bet.get("odd") or 1.0),
                )
                bet["status"] = "WIN" if won else "LOSS"
                bet["profit"] = round(stake * (odd - 1.0), 2) if won else -stake
                bet["result"] = f"{score[0]}:{score[1]}"
                bet["settled_at"] = now.isoformat()
                closing_odd = float(bet.get("closing_odd") or 0.0)
                if closing_odd > 1.0:
                    bet["clv_odds_pct"] = round((odd / closing_odd) - 1.0, 6)
                    captured_devig = float(bet.get("market_probability_devig") or 0.0)
                    closing_devig = float(
                        bet.get("closing_market_probability_devig") or 0.0
                    )
                    if captured_devig > 0.0 and closing_devig > 0.0:
                        bet["clv_probability_pp"] = round(
                            closing_devig - captured_devig, 6
                        )
                changed_bets = True
                settled_bets += 1

            for prediction in predictions:
                if (
                    not _same_fixture(prediction, fixture_id)
                    or str(prediction.get("status", "")).upper() != "PENDING"
                ):
                    continue
                if status in VOID_STATUSES:
                    prediction.update(
                        {
                            "status": "VOID",
                            "outcome": None,
                            "settled_at": now.isoformat(),
                        }
                    )
                    changed_predictions = True
                    settled_predictions += 1
                    continue
                if status in REVIEW_STATUSES:
                    prediction.update(
                        {
                            "status": "REVIEW",
                            "outcome": None,
                            "settled_at": now.isoformat(),
                        }
                    )
                    changed_predictions = True
                    settled_predictions += 1
                    continue
                if status not in FINISHED_STATUSES:
                    continue
                if score is None:
                    prediction.update(
                        {
                            "status": "REVIEW",
                            "outcome": None,
                            "settled_at": now.isoformat(),
                        }
                    )
                    changed_predictions = True
                    settled_predictions += 1
                    continue
                try:
                    outcome = market_outcome(
                        Market.parse(str(prediction["market"])), *score
                    )
                except (KeyError, ValueError):
                    continue
                prediction.update(
                    {
                        "status": "SETTLED",
                        "outcome": int(outcome),
                        "result": f"{score[0]}:{score[1]}",
                        "settled_at": now.isoformat(),
                    }
                )
                changed_predictions = True
                settled_predictions += 1

        if changed_bets:
            self.bet_store.save(bets)
        if changed_predictions:
            self.prediction_store.save(predictions)
        return {
            "settled_bets": settled_bets,
            "settled_predictions": settled_predictions,
            "api_requests": self.api.request_count,
        }


def skip_bet(store: BetStore, identifier: str, now: datetime | None = None) -> bool:
    identifier = identifier.removeprefix("SKIP_").strip()
    timestamp = (now or datetime.now(UTC)).astimezone(UTC).isoformat()

    def mutate(bets: list[dict[str, Any]]) -> bool:
        for bet in bets:
            if (
                str(bet.get("id")) == identifier
                and str(bet.get("status", "")).upper() == "PENDING"
            ):
                bet.update(
                    {"status": "SKIPPED", "profit": 0.0, "skipped_at": timestamp}
                )
                return True
        return False

    return store.update(mutate)
