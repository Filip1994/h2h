from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)).strip())


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)).strip())


@dataclass(frozen=True, slots=True)
class Settings:
    root: Path
    api_key: str
    api_base_url: str
    timezone_name: str
    api_request_budget: int
    api_max_attempts: int
    api_retry_base_seconds: float
    bookmaker_priority: tuple[int, ...]
    allow_any_bookmaker: bool
    excluded_countries: tuple[str, ...]

    bets_file: Path
    predictions_file: Path
    calibration_file: Path
    cache_dir: Path

    initial_bank: float
    paper_mode: bool
    allow_uncalibrated_live: bool
    h2h_telemetry_enabled: bool
    min_odd: float
    max_market_overround: float
    min_h2h_matches: int
    h2h_years: int
    max_recent_h2h_days: int
    min_h2h_rate: float
    min_ev: float
    min_edge: float
    probability_haircut: float
    min_calibration_samples: int
    max_calibration_ece: float
    max_daily_picks: int

    kelly_fraction: float
    max_bet_stake_pct: float
    max_daily_risk_pct: float
    max_open_risk_pct: float
    min_stake: float
    stake_step: float
    drawdown_reduce_at: float
    drawdown_stop_at: float

    dc_xi: float
    dc_ridge: float
    training_seasons: int
    min_training_matches: int
    min_team_matches: int
    max_score_goals: int

    gmail_user: str
    gmail_app_pass: str
    email_to: str
    github_repository: str

    @property
    def timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    @classmethod
    def from_env(cls, root: Path | None = None) -> Settings:
        root = (root or Path(__file__).resolve().parents[2]).resolve()
        bookmaker_priority = tuple(
            int(value.strip())
            for value in os.getenv("BOOKMAKER_PRIORITY", "8,11,6").split(",")
            if value.strip()
        )
        excluded_countries = tuple(
            value.strip().casefold()
            for value in os.getenv("EXCLUDED_COUNTRIES", "").split(",")
            if value.strip()
        )
        settings = cls(
            root=root,
            api_key=os.getenv("API_FOOTBALL_KEY", "").strip(),
            api_base_url=os.getenv(
                "API_FOOTBALL_BASE_URL", "https://v3.football.api-sports.io"
            ).rstrip("/"),
            timezone_name=os.getenv("TIMEZONE", "Europe/Belgrade").strip(),
            api_request_budget=_int("API_REQUEST_BUDGET", 7000),
            api_max_attempts=_int("API_MAX_ATTEMPTS", 3),
            api_retry_base_seconds=_float("API_RETRY_BASE_SECONDS", 1.0),
            bookmaker_priority=bookmaker_priority,
            allow_any_bookmaker=_bool("ALLOW_ANY_BOOKMAKER", True),
            excluded_countries=excluded_countries,
            bets_file=root / "bets.json",
            predictions_file=root / "predictions.json",
            calibration_file=root / "calibration.json",
            cache_dir=root / ".cache" / "api",
            initial_bank=_float("INITIAL_BANK_RSD", 50_000.0),
            paper_mode=_bool("PAPER_MODE", True),
            allow_uncalibrated_live=_bool("ALLOW_UNCALIBRATED_LIVE", False),
            h2h_telemetry_enabled=_bool("H2H_TELEMETRY_ENABLED", False),
            min_odd=_float("MIN_ODD", 1.45),
            max_market_overround=_float("MAX_MARKET_OVERROUND", 0.20),
            min_h2h_matches=_int("MIN_H2H_MATCHES", 5),
            h2h_years=_int("H2H_YEARS", 4),
            max_recent_h2h_days=_int("MAX_RECENT_H2H_DAYS", 730),
            min_h2h_rate=_float("MIN_H2H_RATE", 0.75),
            min_ev=_float("MIN_EV", 0.05),
            min_edge=_float("MIN_EDGE_PP", 0.03),
            probability_haircut=_float("PROBABILITY_HAIRCUT", 0.03),
            min_calibration_samples=_int("MIN_CALIBRATION_SAMPLES", 200),
            max_calibration_ece=_float("MAX_CALIBRATION_ECE", 0.05),
            max_daily_picks=_int("MAX_DAILY_PICKS", 5),
            kelly_fraction=_float("KELLY_FRACTION", 0.25),
            max_bet_stake_pct=_float("MAX_BET_STAKE_PCT", 0.01),
            max_daily_risk_pct=_float("MAX_DAILY_RISK_PCT", 0.03),
            max_open_risk_pct=_float("MAX_OPEN_RISK_PCT", 0.05),
            min_stake=_float("MIN_STAKE_RSD", 100.0),
            stake_step=_float("STAKE_STEP_RSD", 50.0),
            drawdown_reduce_at=_float("DRAWDOWN_REDUCE_AT", 0.05),
            drawdown_stop_at=_float("DRAWDOWN_STOP_AT", 0.10),
            dc_xi=_float("DIXON_COLES_XI", 0.0015),
            dc_ridge=_float("DIXON_COLES_RIDGE", 0.01),
            training_seasons=_int("TRAINING_SEASONS", 4),
            min_training_matches=_int("MIN_TRAINING_MATCHES", 80),
            min_team_matches=_int("MIN_TEAM_MATCHES", 6),
            max_score_goals=_int("MAX_SCORE_GOALS", 10),
            gmail_user=os.getenv("GMAIL_USER", "").strip(),
            gmail_app_pass=os.getenv("GMAIL_APP_PASS", "").strip(),
            email_to=os.getenv("EMAIL_TO", "").strip()
            or os.getenv("GMAIL_USER", "").strip(),
            github_repository=os.getenv("GITHUB_REPOSITORY", "Filip1994/h2h").strip(),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        probabilities = {
            "MIN_H2H_RATE": self.min_h2h_rate,
            "MIN_EV": self.min_ev,
            "MIN_EDGE_PP": self.min_edge,
            "PROBABILITY_HAIRCUT": self.probability_haircut,
            "MAX_MARKET_OVERROUND": self.max_market_overround,
            "MAX_CALIBRATION_ECE": self.max_calibration_ece,
            "KELLY_FRACTION": self.kelly_fraction,
            "MAX_BET_STAKE_PCT": self.max_bet_stake_pct,
            "MAX_DAILY_RISK_PCT": self.max_daily_risk_pct,
            "MAX_OPEN_RISK_PCT": self.max_open_risk_pct,
            "DRAWDOWN_REDUCE_AT": self.drawdown_reduce_at,
            "DRAWDOWN_STOP_AT": self.drawdown_stop_at,
        }
        for name, value in probabilities.items():
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} mora biti između 0 i 1; dobijeno {value}")
        if self.min_odd <= 1.0:
            raise ValueError("MIN_ODD mora biti > 1.0")
        if self.min_h2h_matches < 5:
            raise ValueError("MIN_H2H_MATCHES ne sme biti manji od 5")
        if self.h2h_years < 1 or self.max_recent_h2h_days < 1:
            raise ValueError("H2H prozor i prag svežine moraju biti pozitivni")
        if self.drawdown_reduce_at >= self.drawdown_stop_at:
            raise ValueError("DRAWDOWN_REDUCE_AT mora biti manji od DRAWDOWN_STOP_AT")
        if self.api_request_budget < 1:
            raise ValueError("API_REQUEST_BUDGET mora biti pozitivan")
        if self.api_max_attempts < 1:
            raise ValueError("API_MAX_ATTEMPTS mora biti najmanje 1")
        if not 0.0 <= self.api_retry_base_seconds <= 30.0:
            raise ValueError("API_RETRY_BASE_SECONDS mora biti između 0 i 30")
        if self.min_stake <= 0.0 or self.stake_step <= 0.0:
            raise ValueError("MIN_STAKE_RSD i STAKE_STEP_RSD moraju biti pozitivni")
        if self.max_daily_picks < 1:
            raise ValueError("MAX_DAILY_PICKS mora biti najmanje 1")
        if self.min_calibration_samples < 1:
            raise ValueError("MIN_CALIBRATION_SAMPLES mora biti najmanje 1")
        if self.training_seasons < 1:
            raise ValueError("TRAINING_SEASONS mora biti najmanje 1")
        if self.dc_xi < 0.0 or self.dc_ridge < 0.0:
            raise ValueError(
                "DIXON_COLES_XI i DIXON_COLES_RIDGE ne smeju biti negativni"
            )
        if self.min_training_matches < 1 or self.min_team_matches < 1:
            raise ValueError("Minimalni trening uzorci moraju biti pozitivni")
        if self.max_score_goals < 3:
            raise ValueError("MAX_SCORE_GOALS mora biti najmanje 3")
        if self.initial_bank <= 0.0:
            raise ValueError("INITIAL_BANK_RSD mora biti pozitivan")
        if not self.timezone_name:
            raise ValueError("TIMEZONE ne sme biti prazan")
        _ = self.timezone
