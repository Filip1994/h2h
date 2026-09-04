from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from itertools import groupby
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from quantbot import MODEL_VERSION
from quantbot.calibration import refit_calibration
from quantbot.config import Settings
from quantbot.dixon_coles import DixonColesFitError, DixonColesModel
from quantbot.h2h import build_h2h_stats_from_records, subtract_years
from quantbot.monitor import market_outcome
from quantbot.parsing import parse_datetime
from quantbot.types import Market, MatchRecord

ODDS_COLUMNS = {
    Market.OVER_25: ("over_2_5_odd", "under_2_5_odd"),
    Market.UNDER_25: ("under_2_5_odd", "over_2_5_odd"),
    Market.BTTS_YES: ("btts_yes_odd", "btts_no_odd"),
}
ALL_ODDS_COLUMNS = frozenset(
    column for pair in ODDS_COLUMNS.values() for column in pair
)


def _float_or_none(value: str | None) -> float | None:
    try:
        parsed = float(value or "")
    except ValueError:
        return None
    return parsed if parsed > 1.0 else None


def _record(row: dict[str, str], row_number: int) -> MatchRecord:
    date = parse_datetime(row["date"])
    return MatchRecord(
        fixture_id=int(row.get("fixture_id") or row_number),
        date=date,
        league_id=int(row["league_id"]),
        league_name=row.get("league_name") or "League",
        country=row.get("country") or "Country",
        season=int(row.get("season") or date.year),
        home_id=int(row["home_id"]),
        home_name=row.get("home_name") or str(row["home_id"]),
        away_id=int(row["away_id"]),
        away_name=row.get("away_name") or str(row["away_id"]),
        home_goals=int(row["home_goals"]),
        away_goals=int(row["away_goals"]),
    )


def validate_odds_snapshot(
    row: dict[str, str], record: MatchRecord, row_number: int
) -> datetime | None:
    has_odds = any(_float_or_none(row.get(column)) for column in ALL_ODDS_COLUMNS)
    if not has_odds:
        return None
    if not str(row.get("bookmaker_id") or "").strip():
        raise ValueError(
            f"Red {row_number}: bookmaker_id je obavezan za proverljiv ROI"
        )
    raw_timestamp = str(row.get("odds_captured_at") or "").strip()
    if not raw_timestamp:
        raise ValueError(
            f"Red {row_number}: odds_captured_at je obavezan za proverljiv ROI"
        )
    captured_at = parse_datetime(raw_timestamp)
    if captured_at >= record.date:
        raise ValueError(
            f"Red {row_number}: kvote nisu pre-match ({captured_at.isoformat()} >= "
            f"{record.date.isoformat()})"
        )
    return captured_at


def _brier(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    return sum(
        (float(row["model_probability"]) - int(row["outcome"])) ** 2 for row in rows
    ) / len(rows)


def _log_loss(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    total = 0.0
    for row in rows:
        probability = min(1.0 - 1e-10, max(1e-10, float(row["model_probability"])))
        outcome = int(row["outcome"])
        total -= outcome * math.log(probability) + (1 - outcome) * math.log(
            1.0 - probability
        )
    return total / len(rows)


def selection_statistics(selected: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(
        selected,
        key=lambda row: (str(row["kickoff"]), int(row["event_id"])),
    )
    returns = [float(row["profit_units"]) for row in ordered]
    total = len(returns)
    roi = (sum(returns) / total) if total else None

    equity = 0.0
    peak = 0.0
    max_drawdown_units = 0.0
    losing_streak = 0
    max_losing_streak = 0
    for profit in returns:
        equity += profit
        peak = max(peak, equity)
        max_drawdown_units = max(max_drawdown_units, peak - equity)
        losing_streak = losing_streak + 1 if profit < 0.0 else 0
        max_losing_streak = max(max_losing_streak, losing_streak)

    daily_clusters: dict[str, list[float]] = defaultdict(list)
    for row in ordered:
        daily_clusters[str(row["kickoff"])[:10]].append(float(row["profit_units"]))
    confidence_interval: list[float] | None = None
    if len(daily_clusters) >= 30:
        cluster_values = list(daily_clusters.values())
        cluster_profit = np.asarray([sum(values) for values in cluster_values])
        cluster_count = np.asarray([len(values) for values in cluster_values])
        rng = np.random.default_rng(20_260_904)
        bootstrap_roi = np.empty(10_000, dtype=float)
        for index in range(len(bootstrap_roi)):
            sample = rng.integers(0, len(cluster_values), size=len(cluster_values))
            bootstrap_roi[index] = float(cluster_profit[sample].sum()) / float(
                cluster_count[sample].sum()
            )
        confidence_interval = [
            round(float(value), 8)
            for value in np.quantile(bootstrap_roi, [0.025, 0.975])
        ]

    per_market: dict[str, dict[str, float | int]] = {}
    for market in Market:
        market_rows = [row for row in ordered if row["market"] == market.value]
        if not market_rows:
            continue
        profits = [float(row["profit_units"]) for row in market_rows]
        per_market[market.value] = {
            "n": len(profits),
            "roi": sum(profits) / len(profits),
        }

    return {
        "selected_bets": total,
        "wins": sum(1 for value in returns if value > 0.0),
        "win_rate": (
            sum(1 for value in returns if value > 0.0) / total if total else None
        ),
        "flat_stake_roi": roi,
        "roi_95_ci_day_cluster_bootstrap": confidence_interval,
        "independent_matchdays": len(daily_clusters),
        "max_drawdown_flat_stake_units": max_drawdown_units,
        "max_losing_streak": max_losing_streak,
        "per_market": per_market,
    }


def run_backtest(
    input_path: Path,
    predictions_path: Path,
    report_path: Path,
    calibration_path: Path,
    refit_days: int,
) -> None:
    settings = Settings.from_env(ROOT)
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        raw_rows = list(csv.DictReader(handle))
    records_and_rows: list[tuple[MatchRecord, dict[str, str]]] = []
    for index, row in enumerate(raw_rows, start=1):
        record = _record(row, index)
        validate_odds_snapshot(row, record, index)
        records_and_rows.append((record, row))
    records_and_rows.sort(
        key=lambda item: (item[0].league_id, item[0].date, item[0].fixture_id)
    )

    predictions: list[dict[str, Any]] = []
    selected_results: list[dict[str, Any]] = []
    diagnostics: list[str] = []

    for league_id, league_items_iter in groupby(
        records_and_rows, key=lambda item: item[0].league_id
    ):
        league_items = list(league_items_iter)
        history: list[MatchRecord] = []
        model: DixonColesModel | None = None
        model_fitted_at: datetime | None = None

        for match_date, day_items_iter in groupby(
            league_items, key=lambda item: item[0].date.date()
        ):
            day_items = list(day_items_iter)
            reference_time = datetime.combine(
                match_date, datetime.min.time(), tzinfo=UTC
            )
            rolling_history = [
                record
                for record in history
                if record.date
                >= subtract_years(reference_time, settings.training_seasons)
            ]
            needs_refit = (
                model is None
                or model_fitted_at is None
                or reference_time - model_fitted_at >= timedelta(days=refit_days)
                or any(
                    record.home_id not in model.team_ids
                    or record.away_id not in model.team_ids
                    for record, _row in day_items
                )
            )
            if needs_refit and len(rolling_history) >= settings.min_training_matches:
                try:
                    model = DixonColesModel.fit(
                        rolling_history,
                        reference_time=reference_time,
                        xi=settings.dc_xi,
                        ridge=settings.dc_ridge,
                        min_matches=settings.min_training_matches,
                    )
                    model_fitted_at = reference_time
                except DixonColesFitError as exc:
                    diagnostics.append(f"league_{league_id}_{match_date}: {exc}")
                    model = None

            if model is not None:
                counts = DixonColesModel.team_match_counts(rolling_history)
                for record, raw_row in day_items:
                    if (
                        record.home_id not in model.team_ids
                        or record.away_id not in model.team_ids
                    ):
                        continue
                    if (
                        counts[record.home_id] < settings.min_team_matches
                        or counts[record.away_id] < settings.min_team_matches
                    ):
                        continue
                    pair = {record.home_id, record.away_id}
                    prior_h2h = [
                        past
                        for past in rolling_history
                        if {past.home_id, past.away_id} == pair
                    ]
                    h2h = build_h2h_stats_from_records(
                        prior_h2h, now=record.date, settings=settings
                    )
                    if h2h is None:
                        continue
                    probabilities = model.market_probabilities(
                        record.home_id, record.away_id, settings.max_score_goals
                    )
                    fixture_candidates: list[tuple[float, dict[str, Any]]] = []

                    for market in Market:
                        outcome = int(
                            market_outcome(market, record.home_goals, record.away_goals)
                        )
                        target_column, opposite_column = ODDS_COLUMNS[market]
                        odd = _float_or_none(raw_row.get(target_column))
                        opposite_odd = _float_or_none(raw_row.get(opposite_column))
                        probability = probabilities[market]
                        prediction = {
                            "id": f"{record.fixture_id}_{market.value}_{MODEL_VERSION}_BACKTEST",
                            "event_id": record.fixture_id,
                            "kickoff": record.date.isoformat(),
                            "created_at": record.date.isoformat(),
                            "league_id": record.league_id,
                            "league": f"{record.country} - {record.league_name}",
                            "home_id": record.home_id,
                            "away_id": record.away_id,
                            "match": f"{record.home_name} vs {record.away_name}",
                            "market": market.value,
                            "model_probability": round(probability, 8),
                            "calibrated_probability": round(probability, 8),
                            "calibration_status": "WALK_FORWARD_RAW",
                            "h2h_rate": round(h2h.weighted_rates[market], 8),
                            "h2h_n": len(h2h.matches),
                            "h2h_effective_n": round(h2h.effective_n, 4),
                            "h2h_eligible": h2h.weighted_rates[market]
                            >= settings.min_h2h_rate,
                            "odd": odd,
                            "opposite_odd": opposite_odd,
                            "bookmaker_id": raw_row.get("bookmaker_id") or None,
                            "odds_captured_at": raw_row.get("odds_captured_at") or None,
                            "selected": False,
                            "status": "SETTLED",
                            "outcome": outcome,
                            "model_version": MODEL_VERSION,
                        }
                        predictions.append(prediction)

                        if (
                            not prediction["h2h_eligible"]
                            or odd is None
                            or opposite_odd is None
                            or odd < settings.min_odd
                        ):
                            continue
                        overround = (1.0 / odd) + (1.0 / opposite_odd) - 1.0
                        if not 0.0 <= overround <= settings.max_market_overround:
                            continue
                        decision_probability = max(
                            0.0, probability - settings.probability_haircut
                        )
                        devig_probability = (1.0 / odd) / (
                            (1.0 / odd) + (1.0 / opposite_odd)
                        )
                        expected_value = decision_probability * odd - 1.0
                        edge = decision_probability - devig_probability
                        if (
                            expected_value >= settings.min_ev
                            and edge >= settings.min_edge
                        ):
                            fixture_candidates.append((expected_value, prediction))

                    if fixture_candidates:
                        expected_value, best = max(
                            fixture_candidates, key=lambda item: item[0]
                        )
                        best["selected"] = True
                        selected_results.append(
                            {
                                "event_id": record.fixture_id,
                                "kickoff": record.date.isoformat(),
                                "market": best["market"],
                                "profit_units": (float(best["odd"]) - 1.0)
                                if int(best["outcome"])
                                else -1.0,
                            }
                        )

            history.extend(record for record, _row in day_items)

    predictions_path.parent.mkdir(parents=True, exist_ok=True)
    predictions_path.write_text(
        json.dumps(predictions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    calibration = refit_calibration(
        predictions_path,
        calibration_path,
        min_samples=settings.min_calibration_samples,
        max_ece=settings.max_calibration_ece,
        preserve_existing=False,
    )
    by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for prediction in predictions:
        by_market[str(prediction["market"])].append(prediction)
    report = {
        "model_version": MODEL_VERSION,
        "selection_probability_policy": "RAW_OOS_PROBABILITY_MINUS_HAIRCUT",
        "input_matches": len(records_and_rows),
        "oos_predictions": len(predictions),
        "selection": selection_statistics(selected_results),
        "markets": {
            market: {"n": len(rows), "brier": _brier(rows), "log_loss": _log_loss(rows)}
            for market, rows in by_market.items()
        },
        "calibration": calibration,
        "diagnostics": diagnostics,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Walk-forward Dixon–Coles backtest")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--predictions-output",
        type=Path,
        default=ROOT / "data" / "backtest_predictions.json",
    )
    parser.add_argument(
        "--report-output", type=Path, default=ROOT / "data" / "backtest_report.json"
    )
    parser.add_argument(
        "--calibration-output", type=Path, default=ROOT / "calibration.json"
    )
    parser.add_argument("--refit-days", type=int, default=14)
    args = parser.parse_args()
    run_backtest(
        args.input,
        args.predictions_output,
        args.report_output,
        args.calibration_output,
        args.refit_days,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
