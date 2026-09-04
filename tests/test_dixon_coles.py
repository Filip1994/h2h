from datetime import UTC, datetime, timedelta

import pytest

from quantbot.dixon_coles import DixonColesModel, dixon_coles_tau
from quantbot.types import Market, MatchRecord


def synthetic_records() -> list[MatchRecord]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    records: list[MatchRecord] = []
    fixture_id = 1
    teams = list(range(1, 7))
    for round_index in range(10):
        for home in teams:
            for away in teams:
                if home == away:
                    continue
                home_goals = (home + round_index + away) % 4
                away_goals = (2 * away + round_index + home) % 3
                records.append(
                    MatchRecord(
                        fixture_id=fixture_id,
                        date=start + timedelta(days=fixture_id),
                        league_id=1,
                        league_name="League",
                        country="Country",
                        season=2024,
                        home_id=home,
                        home_name=str(home),
                        away_id=away,
                        away_name=str(away),
                        home_goals=home_goals,
                        away_goals=away_goals,
                    )
                )
                fixture_id += 1
    return records


def test_tau_low_score_correction() -> None:
    assert dixon_coles_tau(0, 0, 1.4, 1.1, -0.05) == pytest.approx(1.077)
    assert dixon_coles_tau(2, 1, 1.4, 1.1, -0.05) == 1.0


def test_fit_and_market_probabilities_are_coherent() -> None:
    records = synthetic_records()
    reference = records[-1].date + timedelta(days=1)
    model = DixonColesModel.fit(
        records, reference_time=reference, xi=0.0015, min_matches=80
    )
    probabilities = model.market_probabilities(1, 2, max_goals=10)
    assert probabilities[Market.OVER_25] + probabilities[
        Market.UNDER_25
    ] == pytest.approx(1.0)
    assert all(0.0 < value < 1.0 for value in probabilities.values())
    assert -0.20 <= model.rho <= 0.20
    assert float(model.attacks.sum()) == pytest.approx(0.0, abs=1e-10)
    assert float(model.defenses.sum()) == pytest.approx(0.0, abs=1e-10)
