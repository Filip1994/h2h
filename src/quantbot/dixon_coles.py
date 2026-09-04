from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

import numpy as np
from scipy.optimize import minimize

from .types import Market, MatchRecord


class DixonColesFitError(RuntimeError):
    pass


def _sum_zero_basis(size: int) -> np.ndarray:
    """Orthonormal Helmert basis for vectors whose elements sum to zero."""
    basis = np.zeros((size, size - 1), dtype=float)
    for column in range(size - 1):
        denominator = math.sqrt((column + 1) * (column + 2))
        basis[: column + 1, column] = 1.0 / denominator
        basis[column + 1, column] = -(column + 1) / denominator
    return basis


def dixon_coles_tau(
    home_goals: int, away_goals: int, lambda_home: float, lambda_away: float, rho: float
) -> float:
    if home_goals == 0 and away_goals == 0:
        return 1.0 - (lambda_home * lambda_away * rho)
    if home_goals == 0 and away_goals == 1:
        return 1.0 + (lambda_home * rho)
    if home_goals == 1 and away_goals == 0:
        return 1.0 + (lambda_away * rho)
    if home_goals == 1 and away_goals == 1:
        return 1.0 - rho
    return 1.0


@dataclass(slots=True)
class DixonColesModel:
    team_ids: tuple[int, ...]
    attacks: np.ndarray
    defenses: np.ndarray
    intercept: float
    home_advantage: float
    rho: float
    xi: float
    fitted_matches: int
    objective: float

    @classmethod
    def fit(
        cls,
        records: list[MatchRecord],
        *,
        reference_time: datetime,
        xi: float,
        ridge: float = 0.01,
        min_matches: int = 80,
    ) -> DixonColesModel:
        records = [record for record in records if record.date < reference_time]
        if len(records) < min_matches:
            raise DixonColesFitError(
                f"Premalo trening mečeva: {len(records)} < {min_matches}"
            )

        team_ids = tuple(
            sorted(
                {record.home_id for record in records}
                | {record.away_id for record in records}
            )
        )
        if len(team_ids) < 4:
            raise DixonColesFitError("Potrebna su najmanje četiri povezana tima")
        team_index = {team_id: index for index, team_id in enumerate(team_ids)}
        n_teams = len(team_ids)
        contrast = _sum_zero_basis(n_teams)

        home_indices = np.asarray(
            [team_index[record.home_id] for record in records], dtype=np.int64
        )
        away_indices = np.asarray(
            [team_index[record.away_id] for record in records], dtype=np.int64
        )
        home_goals = np.asarray(
            [record.home_goals for record in records], dtype=np.int64
        )
        away_goals = np.asarray(
            [record.away_goals for record in records], dtype=np.int64
        )
        ages = np.asarray(
            [
                max(0.0, (reference_time - record.date).total_seconds() / 86_400.0)
                for record in records
            ],
            dtype=float,
        )
        weights = np.exp(-xi * ages)

        mean_goals = max(0.2, float(np.mean(np.concatenate([home_goals, away_goals]))))
        initial = np.zeros(2 * (n_teams - 1) + 3, dtype=float)
        initial[-3] = math.log(mean_goals)
        initial[-2] = 0.10
        initial[-1] = -0.05

        def unpack(
            params: np.ndarray,
        ) -> tuple[np.ndarray, np.ndarray, float, float, float]:
            free_attacks = params[: n_teams - 1]
            free_defenses = params[n_teams - 1 : 2 * (n_teams - 1)]
            attacks = contrast @ free_attacks
            defenses = contrast @ free_defenses
            intercept, home_advantage, rho = params[-3:]
            return (
                attacks,
                defenses,
                float(intercept),
                float(home_advantage),
                float(rho),
            )

        def objective(params: np.ndarray) -> float:
            attacks, defenses, intercept, home_advantage, rho = unpack(params)
            log_lambda_home = np.clip(
                intercept
                + home_advantage
                + attacks[home_indices]
                + defenses[away_indices],
                -5.0,
                3.0,
            )
            log_lambda_away = np.clip(
                intercept + attacks[away_indices] + defenses[home_indices],
                -5.0,
                3.0,
            )
            lambda_home = np.exp(log_lambda_home)
            lambda_away = np.exp(log_lambda_away)

            valid_corrections = (
                (1.0 - lambda_home * lambda_away * rho > 1e-10)
                & (1.0 + lambda_home * rho > 1e-10)
                & (1.0 + lambda_away * rho > 1e-10)
                & (1.0 - rho > 1e-10)
            )
            if not np.all(valid_corrections):
                return 1e12

            log_likelihood = (
                home_goals * log_lambda_home
                - lambda_home
                - np.asarray([math.lgamma(int(value) + 1) for value in home_goals])
                + away_goals * log_lambda_away
                - lambda_away
                - np.asarray([math.lgamma(int(value) + 1) for value in away_goals])
            )

            tau = np.ones(len(records), dtype=float)
            masks = {
                (0, 0): (home_goals == 0) & (away_goals == 0),
                (0, 1): (home_goals == 0) & (away_goals == 1),
                (1, 0): (home_goals == 1) & (away_goals == 0),
                (1, 1): (home_goals == 1) & (away_goals == 1),
            }
            tau[masks[(0, 0)]] = (
                1.0 - lambda_home[masks[(0, 0)]] * lambda_away[masks[(0, 0)]] * rho
            )
            tau[masks[(0, 1)]] = 1.0 + lambda_home[masks[(0, 1)]] * rho
            tau[masks[(1, 0)]] = 1.0 + lambda_away[masks[(1, 0)]] * rho
            tau[masks[(1, 1)]] = 1.0 - rho
            if np.any(tau <= 1e-10) or not np.all(np.isfinite(tau)):
                return 1e12

            penalty = ridge * (
                float(np.dot(attacks, attacks)) + float(np.dot(defenses, defenses))
            )
            return -float(np.sum(weights * (log_likelihood + np.log(tau)))) + penalty

        bounds = (
            [(-3.0, 3.0)] * (n_teams - 1)
            + [(-3.0, 3.0)] * (n_teams - 1)
            + [(-2.0, 2.0), (-1.0, 1.0), (-0.20, 0.20)]
        )
        result = minimize(
            objective,
            initial,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": 2_000, "ftol": 1e-10},
        )
        if not result.success or not np.isfinite(result.fun):
            raise DixonColesFitError(
                f"Optimizacija nije konvergirala: {result.message}"
            )

        attacks, defenses, intercept, home_advantage, rho = unpack(result.x)
        return cls(
            team_ids=team_ids,
            attacks=attacks,
            defenses=defenses,
            intercept=intercept,
            home_advantage=home_advantage,
            rho=rho,
            xi=xi,
            fitted_matches=len(records),
            objective=float(result.fun),
        )

    def expected_goals(self, home_id: int, away_id: int) -> tuple[float, float]:
        index = {team_id: position for position, team_id in enumerate(self.team_ids)}
        if home_id not in index or away_id not in index:
            raise DixonColesFitError("Jedan od timova ne postoji u trening uzorku")
        home_index, away_index = index[home_id], index[away_id]
        lambda_home = math.exp(
            float(
                np.clip(
                    self.intercept
                    + self.home_advantage
                    + self.attacks[home_index]
                    + self.defenses[away_index],
                    -5.0,
                    3.0,
                )
            )
        )
        lambda_away = math.exp(
            float(
                np.clip(
                    self.intercept
                    + self.attacks[away_index]
                    + self.defenses[home_index],
                    -5.0,
                    3.0,
                )
            )
        )
        return lambda_home, lambda_away

    def score_matrix(
        self, home_id: int, away_id: int, max_goals: int = 10
    ) -> np.ndarray:
        lambda_home, lambda_away = self.expected_goals(home_id, away_id)
        goals = np.arange(max_goals + 1)
        home_pmf = np.asarray(
            [
                math.exp(-lambda_home)
                * lambda_home ** int(goal)
                / math.factorial(int(goal))
                for goal in goals
            ]
        )
        away_pmf = np.asarray(
            [
                math.exp(-lambda_away)
                * lambda_away ** int(goal)
                / math.factorial(int(goal))
                for goal in goals
            ]
        )
        matrix = np.outer(home_pmf, away_pmf)
        corrections = [
            dixon_coles_tau(0, 0, lambda_home, lambda_away, self.rho),
            dixon_coles_tau(0, 1, lambda_home, lambda_away, self.rho),
            dixon_coles_tau(1, 0, lambda_home, lambda_away, self.rho),
            dixon_coles_tau(1, 1, lambda_home, lambda_away, self.rho),
        ]
        if any(correction <= 0.0 for correction in corrections):
            raise DixonColesFitError(
                "ρ daje nevalidnu low-score korekciju za ovaj fixture"
            )
        for home_goals in (0, 1):
            for away_goals in (0, 1):
                matrix[home_goals, away_goals] *= dixon_coles_tau(
                    home_goals,
                    away_goals,
                    lambda_home,
                    lambda_away,
                    self.rho,
                )
        total = float(matrix.sum())
        if total <= 0.0 or not np.isfinite(total):
            raise DixonColesFitError("Nevalidna score matrica")
        return matrix / total

    def market_probabilities(
        self, home_id: int, away_id: int, max_goals: int = 10
    ) -> dict[Market, float]:
        matrix = self.score_matrix(home_id, away_id, max_goals=max_goals)
        under = sum(
            float(matrix[home_goals, away_goals])
            for home_goals in range(matrix.shape[0])
            for away_goals in range(matrix.shape[1])
            if home_goals + away_goals <= 2
        )
        btts = float(matrix[1:, 1:].sum())
        return {
            Market.OVER_25: 1.0 - under,
            Market.UNDER_25: under,
            Market.BTTS_YES: btts,
        }

    @staticmethod
    def team_match_counts(records: list[MatchRecord]) -> Counter[int]:
        counts: Counter[int] = Counter()
        for record in records:
            counts[record.home_id] += 1
            counts[record.away_id] += 1
        return counts
