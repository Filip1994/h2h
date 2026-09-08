from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from . import MODEL_VERSION
from .api import APIBudgetExceeded, APIError, APIFootballClient
from .calibration import ProbabilityCalibrator
from .config import Settings
from .dixon_coles import DixonColesFitError, DixonColesModel
from .filters import is_allowed_match
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
    """Generate decisions from one immutable point-in-time data snapshot."""

    def __init__(
        self, settings: Settings, api=None, bet_store=None, prediction_store=None
    ):
        self.settings = settings
        self.api = api or APIFootballClient(settings)
        self.bet_store = bet_store or BetStore(settings.bets_file)
        self.prediction_store = prediction_store or PredictionStore(
            settings.predictions_file
        )
        self.calibrator = ProbabilityCalibrator.load(
            settings.calibration_file, min_samples=settings.min_calibration_samples
        )
        self._model_cache: dict[tuple[int, int, str], DixonColesModel] = {}
        self._training_cache: dict[tuple[int, int, str], list[MatchRecord]] = {}

    def _training_records(
        self, league_id: int, season: int, data_cutoff: datetime
    ) -> list[MatchRecord]:
        cutoff = data_cutoff.astimezone(UTC)
        key = (league_id, season, cutoff.isoformat())
        if key in self._training_cache:
            return self._training_cache[key]
        records_by_id: dict[int, MatchRecord] = {}
        for training_season in range(
            season, season - self.settings.training_seasons, -1
        ):
            for raw in self.api.league_season_fixtures(league_id, training_season):
                try:
                    record = match_record_from_api(raw, require_ft=True)
                except (TypeError, ValueError):
                    continue
                if record.date >= cutoff:
                    continue
                if not is_allowed_match(
                    record.country,
                    record.league_name,
                    record.home_name,
                    record.away_name,
                    self.settings.excluded_countries,
                ):
                    continue
                records_by_id[record.fixture_id] = record
        records = sorted(records_by_id.values(), key=lambda item: item.date)
        self._training_cache[key] = records
        return records

    def _model_for_fixture(
        self, fields: dict[str, Any], *, data_cutoff: datetime
    ) -> DixonColesModel:
        cutoff = data_cutoff.astimezone(UTC)
        key = (int(fields["league_id"]), int(fields["season"]), cutoff.isoformat())
        if key in self._model_cache:
            return self._model_cache[key]
        records = self._training_records(key[0], key[1], cutoff)
        counts = DixonColesModel.team_match_counts(records)
        if counts[int(fields["home_id"])] < self.settings.min_team_matches:
            raise DixonColesFitError("Domaći tim nema dovoljan trening uzorak")
        if counts[int(fields["away_id"])] < self.settings.min_team_matches:
            raise DixonColesFitError("Gostujući tim nema dovoljan trening uzorak")
        model = DixonColesModel.fit(
            records,
            reference_time=cutoff,
            xi=self.settings.dc_xi,
            ridge=self.settings.dc_ridge,
            min_matches=self.settings.min_training_matches,
        )
        self._model_cache[key] = model
        return model

    def _prediction_record(
        self,
        fields,
        market,
        model_probability,
        calibrated_probability,
        calibration_status,
        quote,
        created_at,
        *,
        rejection_reason=None,
        selected=False,
    ):
        return {
            "id": f"{fields['fixture_id']}_{market.value}_{MODEL_VERSION}",
            "event_id": fields["fixture_id"],
            "kickoff": fields["kickoff"].isoformat(),
            "created_at": created_at.isoformat(),
            "decision_timestamp": created_at.astimezone(UTC).isoformat(),
            "data_cutoff": created_at.astimezone(UTC).isoformat(),
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
            if not is_allowed_match(
                fields["country"],
                fields["league_name"],
                fields["home_name"],
                fields["away_name"],
                self.settings.excluded_countries,
            ):
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
                quotes = extract_best_quotes(
                    self.api.odds(fixture_id),
                    bookmaker_priority=self.settings.bookmaker_priority,
                    allow_any_bookmaker=self.settings.allow_any_bookmaker,
                    captured_at=decision_timestamp,
                )
                if not quotes:
                    telemetry["fixtures_without_odds"] += 1
            except APIBudgetExceeded:
                diagnostics.append("API budžet dostignut; skeniranje zaustavljeno")
                break
            except (APIError, DixonColesFitError, ArithmeticError, ValueError) as exc:
                if isinstance(exc, APIError):
                    telemetry["fixture_failures"]["api"] += 1
                elif isinstance(exc, DixonColesFitError):
                    telemetry["fixture_failures"]["dixon_coles"] += 1
                    if "dovoljan trening" in str(exc):
                        telemetry["training_sample_insufficiency"] += 1
                    else:
                        telemetry["fit_failures"] += 1
                else:
                    telemetry["fixture_failures"]["other"] += 1
                diagnostics.append(f"fixture_{fixture_id}: {exc}")
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
            allocations = [
                (candidate, stake)
                for candidate, stake in allocations
                if candidate.expected_value >= self.settings.strong_signal_min_ev
                and candidate.probability_edge >= self.settings.strong_signal_min_edge
                and stake >= self.settings.strong_signal_min_stake
            ]
        selected_ids = {
            f"{candidate.fixture_id}_{candidate.market.value}_{MODEL_VERSION}"
            for candidate, _ in allocations
        }
        for record in prediction_records:
            if record["id"] in selected_ids:
                record["selected"] = True
                record["rejection_reason"] = None
        self.prediction_store.append_unique(prediction_records)
        mode = "PAPER" if self.settings.paper_mode else "LIVE"
        proposed_bets = [
            candidate.to_bet(
                bet_id=f"{candidate.fixture_id}_{candidate.market.value}",
                stake=stake,
                mode=mode,
                created_at=now_local,
                model_version=MODEL_VERSION,
                xi=self.settings.dc_xi,
            )
            for candidate, stake in allocations
        ]
        signal_source = (
            "INTRADAY_ALERT" if self.settings.intraday_mode else "DAILY_BULLETIN"
        )
        for bet in proposed_bets:
            bet["signal_source"] = signal_source
            bet["signal_sent_at"] = now_local.isoformat()
        appended = self.bet_store.append_unique_fixtures(proposed_bets)
        telemetry["selections_produced"] = len(appended)
        telemetry["funnel"] = {
            "discovered": telemetry["fixtures_discovered"],
            "eligible": telemetry["fixtures_eligible"],
            "modelled": telemetry["fixtures_modelled"],
            "predictions": telemetry["predictions_generated"],
            "candidates": telemetry["candidates"],
            "selections": telemetry["selections_produced"],
        }
        final_bets = self.bet_store.load()
        analytics = portfolio_analytics(
            final_bets, self.settings.initial_bank, today=now_local.date().isoformat()
        )
        diagnostics.append(
            f"scan={len(raw_fixtures)} candidates={len(candidates)} selected={len(appended)} "
            f"api={self.api.request_count} mode={'intraday' if self.settings.intraday_mode else 'daily'}"
        )
        return GenerationResult(
            new_bets=tuple(appended),
            analytics=analytics,
            diagnostics=tuple(diagnostics),
            api_requests=self.api.request_count,
            api_usage=self.api.usage_snapshot(),
            telemetry=telemetry,
        )
