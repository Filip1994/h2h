from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from . import MODEL_VERSION
from .api import APIBudgetExceeded, APIError, APIFootballClient
from .calibration import ProbabilityCalibrator
from .config import Settings
from .dixon_coles import DixonColesFitError, DixonColesModel
from .filters import eligibility_decision
from .markets import extract_best_quotes
from .parsing import current_fixture_fields, match_record_from_api
from .risk import PortfolioAnalytics, allocate_stakes, portfolio_analytics
from .storage import BetStore, PredictionStore
from .types import Market, MarketCandidate, MatchRecord


@dataclass(frozen=True, slots=True)
class GenerationResult:
    new_bets: tuple[dict[str, Any], ...]
    analytics: PortfolioAnalytics
    diagnostics: tuple[str, ...]
    api_requests: int
    api_usage: dict[str, Any]
    telemetry: dict[str, Any]


class QuantEngine:
    def __init__(self, settings: Settings, api: APIFootballClient | None = None) -> None:
        self.settings = settings
        self.api = api or APIFootballClient(settings)
        self.bet_store = BetStore(settings.bets_file)
        self.prediction_store = PredictionStore(settings.predictions_file)
        self.calibrator = ProbabilityCalibrator(settings)
        self._training_cache: dict[tuple[int, int, str], list[MatchRecord]] = {}

    def _model_for_fixture(
        self, fields: dict[str, Any], data_cutoff: datetime
    ) -> DixonColesModel:
        key = (int(fields["league_id"]), int(fields["season"]), data_cutoff.isoformat())
        if key not in self._training_cache:
            self._training_cache[key] = self._training_records(
                int(fields["league_id"]), int(fields["season"]), data_cutoff
            )
        records = self._training_cache[key]
        return DixonColesModel.fit(records, now=data_cutoff)

    def _training_records(
        self, league_id: int, season: int, data_cutoff: datetime
    ) -> list[MatchRecord]:
        cutoff = data_cutoff.astimezone(UTC)
        key = (league_id, season, cutoff.isoformat())
        if key in self._training_cache:
            return self._training_cache[key]
        records = [
            record
            for record in self._load_training_records(league_id, season)
            if record.date < cutoff
        ]
        self._training_cache[key] = records
        return records

    def _prediction_record(
        self,
        fields: dict[str, Any],
        market: Market,
        model_probability: float,
        calibrated_probability: float,
        calibration_status: str,
        quote: Any,
        created_at: datetime,
        rejection_reason: str | None = None,
        selected: bool = False,
    ) -> dict[str, Any]:
        return {
            "event_id": fields["fixture_id"],
            "kickoff": fields["kickoff"].astimezone(UTC).isoformat(),
            "created_at": created_at.astimezone(UTC).isoformat(),
            "league_id": fields["league_id"],
            "league": f"{fields['country']} - {fields['league_name']}",
            "home_id": fields["home_id"],
            "away_id": fields["away_id"],
            "match": f"{fields['home_name']} vs {fields['away_name']}",
            "market": market.value,
            "model_probability": round(model_probability, 6),
            "calibrated_probability": round(calibrated_probability, 6),
            "calibration_status": calibration_status,
            "odd": round(quote.odd, 4) if quote else None,
            "opposite_odd": round(quote.opposite_odd, 4) if quote else None,
            "bookmaker_id": quote.bookmaker_id if quote else None,
            "bookmaker": quote.bookmaker_name if quote else None,
            "odds_captured_at": (quote.captured_at.isoformat() if quote else None),
            "market_probability_devig": round(quote.devig_probability, 6)
            if quote
            else None,
            "market_overround": round(quote.overround, 6) if quote else None,
            "selected": selected,
            "rejection_reason": rejection_reason,
            "status": "PENDING",
            "outcome": None,
            "model_version": MODEL_VERSION,
        }

    def generate(self, now: datetime | None = None) -> GenerationResult:
        now_local = (
            now.astimezone(self.settings.timezone)
            if now
            else datetime.now(self.settings.timezone)
        )
        decision_timestamp = now_local.astimezone(UTC)
        if not self.settings.paper_mode and not self.settings.allow_uncalibrated_live:
            missing = [
                market.value
                for market in Market
                if not self.calibrator.is_validated(market)
            ]
            if missing:
                raise RuntimeError(
                    "LIVE režim odbijen: nema validirane kalibracije za "
                    + ", ".join(missing)
                )
        existing_bets = self.bet_store.load()
        blocked_fixture_ids = self.bet_store.blocked_fixture_ids(existing_bets)
        diagnostics: list[str] = []
        candidates: list[MarketCandidate] = []
        prediction_records: list[dict[str, Any]] = []
        telemetry: dict[str, Any] = {
            "fixtures_discovered": 0,
            "fixtures_parse_failures": 0,
            "fixtures_eligible": 0,
            "fixtures_modelled": 0,
            "predictions_generated": 0,
            "candidates_evaluated": 0,
            "candidates_qualified": 0,
            "candidates": 0,
            "selections_produced": 0,
            "training_sample_insufficiency": 0,
            "fit_failures": 0,
            "fixtures_without_odds": 0,
            "fixture_failures": {"api": 0, "dixon_coles": 0, "other": 0},
            "eligibility_rejections": {},
        }
        raw_fixtures = self.api.fixtures_by_date(now_local.date().isoformat())
        telemetry["fixtures_discovered"] = len(raw_fixtures)
        upper_hours = (
            self.settings.intraday_lookahead_hours
            if self.settings.intraday_mode
            else 24
        )
        for raw_fixture in raw_fixtures:
            try:
                fields = current_fixture_fields(raw_fixture)
            except (TypeError, ValueError) as exc:
                telemetry["fixtures_parse_failures"] += 1
                telemetry["fixture_failures"]["other"] += 1
                diagnostics.append(f"fixture_parse: {exc}")
                continue
            fixture_id = int(fields["fixture_id"])
            if fixture_id in blocked_fixture_ids or fields["status"] not in {
                "NS",
                "TBD",
            }:
                continue
            if not (
                decision_timestamp + timedelta(minutes=15)
                < fields["kickoff"]
                < decision_timestamp + timedelta(hours=upper_hours)
            ):
                continue
            decision = eligibility_decision(
                fields["country"],
                fields["league_id"],
                fields["league_name"],
                fields["home_name"],
                fields["away_name"],
                self.settings.excluded_countries,
            )
            if not decision.eligible:
                telemetry["eligibility_rejections"][decision.reason] = (
                    int(telemetry["eligibility_rejections"].get(decision.reason, 0)) + 1
                )
                continue
            telemetry["fixtures_eligible"] += 1

            try:
                model = self._model_for_fixture(fields, data_cutoff=decision_timestamp)
                model_probabilities = model.market_probabilities(
                    fields["home_id"],
                    fields["away_id"],
                    max_goals=self.settings.max_score_goals,
                )
                lambda_home, lambda_away = model.expected_goals(
                    fields["home_id"], fields["away_id"]
                )
                telemetry["fixtures_modelled"] += 1
                quotes = extract_best_quotes(self.api.odds(fixture_id))
            except APIBudgetExceeded as exc:
                telemetry["fixture_failures"]["api"] += 1
                diagnostics.append(f"fixture_{fixture_id}: {exc}")
                continue
            except APIError as exc:
                telemetry["fixture_failures"]["api"] += 1
                diagnostics.append(f"fixture_{fixture_id}: {exc}")
                continue
            except DixonColesFitError as exc:
                telemetry["fit_failures"] += 1
                telemetry["fixture_failures"]["dixon_coles"] += 1
                diagnostics.append(f"fixture_{fixture_id}: {exc}")
                continue
            except ValueError as exc:
                telemetry["fixture_failures"]["other"] += 1
                diagnostics.append(f"fixture_{fixture_id}: {exc}")
                continue
            if not quotes:
                telemetry["fixtures_without_odds"] += 1
                continue
            fixture_candidates: list[MarketCandidate] = []
            for market in Market:
                telemetry["candidates_evaluated"] += 1
                model_probability = model_probabilities[market]
                calibrated_probability, calibration_status = self.calibrator.apply(
                    market, model_probability
                )
                quote = quotes.get(market)
                decision_probability = max(
                    0.0, calibrated_probability - self.settings.probability_haircut
                )
                reason = None
                expected_value = None
                probability_edge = None
                if quote is None:
                    reason = "REJECT_NO_ODDS"
                elif quote.odd < self.settings.min_odd:
                    reason = "REJECT_ODD"
                elif not (0.0 <= quote.overround <= self.settings.max_market_overround):
                    reason = "REJECT_OVERROUND"
                else:
                    expected_value = decision_probability * quote.odd - 1.0
                    probability_edge = decision_probability - quote.devig_probability
                    if expected_value < self.settings.min_ev:
                        reason = "REJECT_LOW_EV"
                    elif probability_edge < self.settings.min_edge:
                        reason = "REJECT_LOW_EDGE"
                prediction_records.append(
                    self._prediction_record(
                        fields,
                        market,
                        model_probability,
                        calibrated_probability,
                        calibration_status,
                        quote,
                        now_local,
                        rejection_reason=reason,
                    )
                )
                telemetry["predictions_generated"] += 1
                if (
                    reason
                    or quote is None
                    or expected_value is None
                    or probability_edge is None
                ):
                    continue
                fixture_candidates.append(
                    MarketCandidate(
                        fixture_id=fixture_id,
                        kickoff=fields["kickoff"],
                        league_id=fields["league_id"],
                        league_name=fields["league_name"],
                        country=fields["country"],
                        home_id=fields["home_id"],
                        home_name=fields["home_name"],
                        away_id=fields["away_id"],
                        away_name=fields["away_name"],
                        market=market,
                        model_probability=model_probability,
                        calibrated_probability=calibrated_probability,
                        decision_probability=decision_probability,
                        quote=quote,
                        lambda_home=lambda_home,
                        lambda_away=lambda_away,
                        rho=model.rho,
                        expected_value=expected_value,
                        probability_edge=probability_edge,
                        calibration_status=calibration_status,
                    )
                )
            if fixture_candidates:
                telemetry["candidates_qualified"] += len(fixture_candidates)
                telemetry["candidates"] += 1
                candidates.append(
                    max(
                        fixture_candidates,
                        key=lambda item: (item.expected_value, item.probability_edge),
                    )
                )
        allocations = allocate_stakes(
            candidates, existing_bets, now=now_local, settings=self.settings
        )
        if self.settings.intraday_mode:
            self._emit_intraday_alerts(allocations, now_local)
        new_bets = tuple(self.bet_store.append_many(allocations))
        self.prediction_store.append_many(prediction_records)
        analytics = portfolio_analytics(
            self.bet_store.load(), now=now_local, settings=self.settings
        )
        return GenerationResult(
            new_bets=new_bets,
            analytics=analytics,
            diagnostics=tuple(diagnostics),
            api_requests=self.api.request_count,
            api_usage=self.api.usage_snapshot(),
            telemetry=telemetry,
        )
