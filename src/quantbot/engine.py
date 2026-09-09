from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .api import APIBudgetExceeded, APIError
from .calibration import CalibrationError, CalibrationModel
from .config import MODEL_VERSION, Settings
from .dixon_coles import DixonColesFitError, DixonColesModel
from .eligibility import eligibility_decision
from .filters import current_fixture_fields
from .markets import Market, MarketCandidate, extract_best_quotes
from .risk import allocate_stakes
from .storage import BetStore, PredictionStore
from .decision_packet import build_packet


class QuantEngine:
    def __init__(self, settings: Settings, api, bet_store: BetStore, prediction_store: PredictionStore, calibrator: CalibrationModel) -> None:
        self.settings = settings
        self.api = api
        self.bet_store = bet_store
        self.prediction_store = prediction_store
        self.calibrator = calibrator

    def _model_for_fixture(self, fields: dict[str, Any], *, data_cutoff: datetime) -> DixonColesModel:
        history = self.api.league_season_fixtures(fields["league_id"], fields["season"])
        history = [
            match
            for match in history
            if datetime.fromisoformat(str(match["fixture"]["date"]).replace("Z", "+00:00")).astimezone(UTC) < data_cutoff
        ]
        return DixonColesModel.fit_from_api(history, xi=self.settings.dc_xi)

    def generate(self, *, now: datetime | None = None) -> dict[str, Any]:
        now_local = now or datetime.now(self.settings.timezone)
        decision_timestamp = now_local.astimezone(UTC)
        if not self.settings.paper_mode and not self.settings.calibration_validated:
            missing = ["calibration"]
            raise RuntimeError(
                "LIVE režim odbijen: nema validirane kalibracije za " + ", ".join(missing)
            )
        existing_bets = self.bet_store.load()
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
            "funnel_rejections": [],
            "odds_available": 0,
            "valid_quotes": 0,
            "ev_pass": 0,
            "edge_pass": 0,
            "risk_rejections": 0,
            "duplicate_rejections": 0,
            "persistence_failures": 0,
        }
        raw_fixtures = self.api.fixtures_by_date(now_local.date().isoformat())
        telemetry["fixtures_discovered"] = len(raw_fixtures)
        upper_hours = self.settings.intraday_lookahead_hours if self.settings.intraday_mode else 24
        for raw_fixture in raw_fixtures:
            try:
                fields = current_fixture_fields(raw_fixture)
            except (TypeError, ValueError) as exc:
                telemetry["fixtures_parse_failures"] += 1
                telemetry["fixture_failures"]["other"] += 1
                diagnostics.append(f"fixture_parse: {exc}")
                continue
            fixture_id = int(fields["fixture_id"])
            if fields["status"] not in {"NS", "TBD"}:
                continue
            if not (
                decision_timestamp + timedelta(minutes=15)
                < fields["kickoff"]
                < decision_timestamp + timedelta(hours=upper_hours)
            ):
                continue
            decision = eligibility_decision(
                fields["country"], fields["league_id"], fields["league_name"], fields["home_name"], fields["away_name"], self.settings.excluded_countries
            )
            if not decision.eligible:
                telemetry["funnel_rejections"].append({"fixture_id": fixture_id, "stage": "eligible", "reason": decision.reason})
                telemetry["eligibility_rejections"][decision.reason] = int(telemetry["eligibility_rejections"].get(decision.reason, 0)) + 1
                continue
            telemetry["fixtures_eligible"] += 1
            try:
                model = self._model_for_fixture(fields, data_cutoff=decision_timestamp)
                model_probabilities = model.market_probabilities(fields["home_id"], fields["away_id"])
                lambda_home, lambda_away = model.expected_goals(fields["home_id"], fields["away_id"])
                telemetry["fixtures_modelled"] += 1
                quotes = extract_best_quotes(
                    self.api.odds(fixture_id),
                    bookmaker_priority=self.settings.bookmaker_priority,
                    allow_any_bookmaker=self.settings.allow_any_bookmaker,
                    captured_at=decision_timestamp,
                )
                if quotes:
                    telemetry["odds_available"] += 1
                else:
                    telemetry["fixtures_without_odds"] += 1
                    telemetry["funnel_rejections"].append({"fixture_id": fixture_id, "stage": "odds_available", "reason": "NO_ODDS_RESPONSE"})
            except APIBudgetExceeded:
                diagnostics.append("API budžet dostignut; skeniranje zaustavljeno")
                break
            except (APIError, DixonColesFitError, ArithmeticError, ValueError) as exc:
                if isinstance(exc, APIError):
                    telemetry["fixture_failures"]["api"] += 1
                    telemetry["funnel_rejections"].append({"fixture_id": fixture_id, "stage": "modelled", "reason": "API_ERROR"})
                elif isinstance(exc, DixonColesFitError):
                    telemetry["fixture_failures"]["dixon_coles"] += 1
                    if "dovoljan trening" in str(exc):
                        telemetry["training_sample_insufficiency"] += 1
                        telemetry["funnel_rejections"].append({"fixture_id": fixture_id, "stage": "modelled", "reason": "NO_TRAINING_SAMPLE"})
                    else:
                        telemetry["fit_failures"] += 1
                        telemetry["funnel_rejections"].append({"fixture_id": fixture_id, "stage": "modelled", "reason": "MODEL_FIT_FAILURE"})
                else:
                    telemetry["fixture_failures"]["other"] += 1
                diagnostics.append(f"fixture_{fixture_id}: {exc}")
                continue
            fixture_candidates: list[MarketCandidate] = []
            for market in Market:
                telemetry["candidates_evaluated"] += 1
                model_probability = model_probabilities[market]
                calibrated_probability, calibration_status = self.calibrator.apply(market, model_probability)
                quote = quotes.get(market)
                decision_probability = max(model_probability, calibrated_probability) if calibration_status == "VALID" else model_probability
                if quote is None:
                    telemetry["funnel_rejections"].append({"fixture_id": fixture_id, "market": market.value, "stage": "valid_quote", "reason": "MARKET_UNAVAILABLE"})
                    continue
                telemetry["valid_quotes"] += 1
                candidate = MarketCandidate.from_quote(
                    fixture_id=fixture_id,
                    market=market,
                    quote=quote,
                    probability=decision_probability,
                    calibrated_probability=calibrated_probability,
                    lambda_home=lambda_home,
                    lambda_away=lambda_away,
                    rho=model.rho,
                    model_probability=model_probability,
                    calibration_status=calibration_status,
                    model_version=MODEL_VERSION,
                    model_fitted_matches=model.fitted_matches,
                    model_team_count=len(model.team_ids),
                    model_training_cutoff=decision_timestamp.isoformat(),
                    model_training_identity=hashlib.sha256(json.dumps({"fitted_matches": model.fitted_matches, "team_ids": list(model.team_ids)}, sort_keys=True).encode("utf-8")).hexdigest(),
                )
                if candidate.expected_value < self.settings.min_ev:
                    telemetry["funnel_rejections"].append({"fixture_id": fixture_id, "market": market.value, "stage": "ev_pass", "reason": "EV_BELOW_THRESHOLD"})
                    continue
                telemetry["ev_pass"] += 1
                if candidate.probability_edge < self.settings.min_edge:
                    telemetry["funnel_rejections"].append({"fixture_id": fixture_id, "market": market.value, "stage": "edge_pass", "reason": "EDGE_BELOW_THRESHOLD"})
                    continue
                telemetry["edge_pass"] += 1
                fixture_candidates.append(candidate)
            if fixture_candidates:
                telemetry["candidates_qualified"] += len(fixture_candidates)
                telemetry["candidates"] += len(fixture_candidates)
                candidates.extend(fixture_candidates)
        allocations = allocate_stakes(candidates, existing_bets, now=now_local, settings=self.settings)
        if self.settings.intraday_mode:
            allocations = [
                (candidate, stake)
                for candidate, stake in allocations
                if candidate.expected_value >= self.settings.strong_signal_min_ev
                and candidate.probability_edge >= self.settings.strong_signal_min_edge
                and stake >= self.settings.strong_signal_min_stake
            ]
        selected_ids = {f"{candidate.fixture_id}_{candidate.market.value}_{MODEL_VERSION}" for candidate, _ in allocations}
        for record in prediction_records:
            if record["id"] in selected_ids:
                record["selected"] = True
                record["rejection_reason"] = None
        self.prediction_store.append_unique(prediction_records)
        mode = "PAPER" if self.settings.paper_mode else "LIVE"
        proposed_bets = [
            candidate.to_bet(bet_id=f"{candidate.fixture_id}_{candidate.market.value}", stake=stake, mode=mode, created_at=now_local, model_version=MODEL_VERSION, xi=self.settings.dc_xi)
            for candidate, stake in allocations
        ]
        calibration_hash = None
        try:
            calibration_hash = hashlib.sha256(self.settings.calibration_file.read_bytes()).hexdigest()
        except OSError:
            pass
        signal_source = "INTRADAY_ALERT" if self.settings.intraday_mode else "DAILY_BULLETIN"
        candidate_by_id = {f"{candidate.fixture_id}_{candidate.market.value}_{MODEL_VERSION}": (candidate, stake) for candidate, stake in allocations}
        for bet in proposed_bets:
            bet["signal_source"] = signal_source
            bet["signal_sent_at"] = now_local.isoformat()
            candidate_stake = candidate_by_id.get(str(bet.get("prediction_id")))
            if candidate_stake is not None:
                candidate, stake = candidate_stake
                packet = build_packet(candidate, stake, settings=self.settings, decision_timestamp=decision_timestamp, calibration_hash=calibration_hash)
                bet["decision_packet"] = packet
                bet["decision_packet_id"] = packet["packet_id"]
                bet["decision_packet_integrity_hash"] = packet["integrity_hash"]
        try:
            appended = self.bet_store.append_unique_fixtures(proposed_bets)
        except OSError as exc:
            telemetry["persistence_failures"] += 1
            diagnostics.append(f"persistence: {exc}")
            appended = []
        telemetry["selections_produced"] = len(appended)
        return {"bets": appended, "telemetry": telemetry, "diagnostics": diagnostics}
