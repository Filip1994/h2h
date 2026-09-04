from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any


class Market(StrEnum):
    OVER_25 = "OVER_2_5"
    UNDER_25 = "UNDER_2_5"
    BTTS_YES = "BTTS_YES"

    @property
    def display_name(self) -> str:
        return {
            Market.OVER_25: "Ukupno Golova - Više 2.5",
            Market.UNDER_25: "Ukupno Golova - Manje 2.5",
            Market.BTTS_YES: "Oba Tima Daju Gol (GG)",
        }[self]

    @classmethod
    def parse(cls, value: str) -> Market:
        aliases = {
            "OVER_2_5": cls.OVER_25,
            "UNDER_2_5": cls.UNDER_25,
            "BTTS_YES": cls.BTTS_YES,
            "Ukupno Golova - Više 2.5": cls.OVER_25,
            "Ukupno Golova - Manje 2.5": cls.UNDER_25,
            "Oba Tima Daju Gol (GG)": cls.BTTS_YES,
            "Više 2.5 Golova": cls.OVER_25,
        }
        if value in aliases:
            return aliases[value]
        return cls(value)


TERMINAL_STATUSES = frozenset({"WIN", "LOSS", "SKIPPED", "VOID", "REVIEW"})
BLOCKING_STATUSES = TERMINAL_STATUSES | {"PENDING"}


@dataclass(frozen=True, slots=True)
class MatchRecord:
    fixture_id: int
    date: datetime
    league_id: int
    league_name: str
    country: str
    season: int
    home_id: int
    home_name: str
    away_id: int
    away_name: str
    home_goals: int
    away_goals: int
    halftime_home: int | None = None
    halftime_away: int | None = None


@dataclass(frozen=True, slots=True)
class H2HStats:
    matches: tuple[MatchRecord, ...]
    weighted_rates: dict[Market, float]
    effective_n: float
    has_recent_match: bool


@dataclass(frozen=True, slots=True)
class OddsQuote:
    market: Market
    odd: float
    opposite_odd: float
    bookmaker_id: int
    bookmaker_name: str
    captured_at: datetime

    @property
    def implied_probability(self) -> float:
        return 1.0 / self.odd

    @property
    def devig_probability(self) -> float:
        target = 1.0 / self.odd
        opposite = 1.0 / self.opposite_odd
        return target / (target + opposite)

    @property
    def overround(self) -> float:
        return (1.0 / self.odd) + (1.0 / self.opposite_odd) - 1.0


@dataclass(frozen=True, slots=True)
class MarketCandidate:
    fixture_id: int
    kickoff: datetime
    league_id: int
    league_name: str
    country: str
    home_id: int
    home_name: str
    away_id: int
    away_name: str
    market: Market
    model_probability: float
    calibrated_probability: float
    decision_probability: float
    h2h_rate: float
    h2h_n: int
    h2h_effective_n: float
    h2h_history: tuple[str, ...]
    quote: OddsQuote
    lambda_home: float
    lambda_away: float
    rho: float
    expected_value: float
    probability_edge: float
    calibration_status: str

    def to_bet(
        self,
        *,
        bet_id: str,
        stake: float,
        mode: str,
        created_at: datetime,
        model_version: str,
        xi: float,
    ) -> dict[str, Any]:
        return {
            "id": bet_id,
            "type": "DC_H2H_VALUE",
            "mode": mode,
            "event_id": self.fixture_id,
            "created_at": created_at.isoformat(),
            "date": created_at.date().isoformat(),
            "kickoff": self.kickoff.isoformat(),
            "sport": "Football",
            "match": f"{self.home_name} vs {self.away_name}",
            "home_id": self.home_id,
            "away_id": self.away_id,
            "league": f"{self.country} - {self.league_name}",
            "league_id": self.league_id,
            "market": self.market.value,
            "market_display": self.market.display_name,
            "stake": round(stake, 2),
            "odd": round(self.quote.odd, 4),
            "opposite_odd": round(self.quote.opposite_odd, 4),
            "bookmaker_id": self.quote.bookmaker_id,
            "bookmaker": self.quote.bookmaker_name,
            "odds_captured_at": self.quote.captured_at.isoformat(),
            "implied_probability": round(self.quote.implied_probability, 6),
            "market_probability_devig": round(self.quote.devig_probability, 6),
            "market_overround": round(self.quote.overround, 6),
            "model_probability": round(self.model_probability, 6),
            "calibrated_probability": round(self.calibrated_probability, 6),
            "decision_probability": round(self.decision_probability, 6),
            "probability_edge": round(self.probability_edge, 6),
            "expected_value": round(self.expected_value, 6),
            "h2h_rate": round(self.h2h_rate, 6),
            "h2h_n": self.h2h_n,
            "h2h_effective_n": round(self.h2h_effective_n, 3),
            "h2h_history": list(self.h2h_history),
            "lambda_home": round(self.lambda_home, 6),
            "lambda_away": round(self.lambda_away, 6),
            "rho": round(self.rho, 6),
            "xi": xi,
            "model_version": model_version,
            "calibration_status": self.calibration_status,
            "status": "PENDING",
            "profit": 0.0,
        }
