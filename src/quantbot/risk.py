from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .config import Settings
from .types import MarketCandidate


@dataclass(frozen=True, slots=True)
class PortfolioAnalytics:
    current_bank: float
    total_profit: float
    total_stake: float
    roi: float
    win_rate: float
    completed_count: int
    open_stake: float
    current_drawdown: float


def portfolio_analytics(
    bets: list[dict[str, Any]], initial_bank: float
) -> PortfolioAnalytics:
    completed = [
        bet for bet in bets if str(bet.get("status", "")).upper() in {"WIN", "LOSS"}
    ]
    completed.sort(key=lambda bet: str(bet.get("settled_at") or bet.get("date") or ""))
    total_profit = sum(float(bet.get("profit") or 0.0) for bet in completed)
    total_stake = sum(float(bet.get("stake") or 0.0) for bet in completed)
    wins = sum(1 for bet in completed if str(bet.get("status", "")).upper() == "WIN")
    open_stake = sum(
        float(bet.get("stake") or 0.0)
        for bet in bets
        if str(bet.get("status", "")).upper() == "PENDING"
    )

    equity = initial_bank
    peak = initial_bank
    for bet in completed:
        equity += float(bet.get("profit") or 0.0)
        peak = max(peak, equity)
    current_bank = initial_bank + total_profit
    drawdown = (peak - current_bank) / peak if peak > 0.0 else 1.0

    return PortfolioAnalytics(
        current_bank=current_bank,
        total_profit=total_profit,
        total_stake=total_stake,
        roi=(total_profit / total_stake) if total_stake > 0.0 else 0.0,
        win_rate=(wins / len(completed)) if completed else 0.0,
        completed_count=len(completed),
        open_stake=open_stake,
        current_drawdown=max(0.0, drawdown),
    )


def circuit_breaker_multiplier(drawdown: float, settings: Settings) -> float:
    if drawdown >= settings.drawdown_stop_at:
        return 0.0
    if drawdown >= settings.drawdown_reduce_at:
        return 0.5
    return 1.0


def kelly_stake(
    bank: float, probability: float, odd: float, settings: Settings
) -> float:
    if bank <= 0.0 or not 0.0 < probability < 1.0 or odd <= 1.0:
        return 0.0
    full_kelly = ((probability * odd) - 1.0) / (odd - 1.0)
    if full_kelly <= 0.0:
        return 0.0
    raw = bank * full_kelly * settings.kelly_fraction
    capped = min(raw, bank * settings.max_bet_stake_pct)
    rounded_down = math.floor(capped / settings.stake_step) * settings.stake_step
    return rounded_down if rounded_down >= settings.min_stake else 0.0


def allocate_stakes(
    candidates: list[MarketCandidate],
    existing_bets: list[dict[str, Any]],
    *,
    now: datetime,
    settings: Settings,
) -> list[tuple[MarketCandidate, float]]:
    analytics = portfolio_analytics(existing_bets, settings.initial_bank)
    if analytics.current_bank <= 0.0:
        return []
    multiplier = circuit_breaker_multiplier(analytics.current_drawdown, settings)
    if multiplier <= 0.0:
        return []

    today = now.date().isoformat()
    pending = [
        bet for bet in existing_bets if str(bet.get("status", "")).upper() == "PENDING"
    ]
    today_open_stake = sum(
        float(bet.get("stake") or 0.0) for bet in pending if bet.get("date") == today
    )
    today_open_count = sum(1 for bet in pending if bet.get("date") == today)
    daily_remaining = max(
        0.0, analytics.current_bank * settings.max_daily_risk_pct - today_open_stake
    )
    open_remaining = max(
        0.0, analytics.current_bank * settings.max_open_risk_pct - analytics.open_stake
    )
    remaining = min(daily_remaining, open_remaining)
    pick_slots = max(0, settings.max_daily_picks - today_open_count)

    selected: list[tuple[MarketCandidate, float]] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (item.expected_value, item.probability_edge),
        reverse=True,
    ):
        if len(selected) >= pick_slots:
            break
        stake = kelly_stake(
            analytics.current_bank,
            candidate.decision_probability,
            candidate.quote.odd,
            settings,
        )
        stake *= multiplier
        stake = min(stake, remaining)
        stake = math.floor(stake / settings.stake_step) * settings.stake_step
        if stake < settings.min_stake:
            continue
        selected.append((candidate, stake))
        remaining -= stake
        if remaining < settings.min_stake:
            break
    return selected
