from __future__ import annotations

from dataclasses import dataclass
from typing import Any

STRONG_SIGNAL_INITIAL_BANK = 10_000.0


@dataclass(frozen=True, slots=True)
class StrongSignalPortfolio:
    initial_bank: float
    current_bank: float
    total_profit: float
    total_stake: float
    roi: float
    win_rate: float
    completed_count: int
    open_stake: float
    current_drawdown: float


def _terminal(row: dict[str, Any]) -> bool:
    return str(row.get("status") or "").upper() in {"WIN", "LOSS", "VOID", "REVIEW"}


def portfolio(rows: list[dict[str, Any]]) -> StrongSignalPortfolio:
    strong = [
        row for row in rows
        if str(row.get("signal_class") or "").upper() == "STRONG_SIGNAL"
    ]
    completed = [row for row in strong if _terminal(row)]
    total_profit = sum(
        float(row.get("virtual_profit", row.get("profit") or 0.0) or 0.0)
        for row in completed
    )
    total_stake = sum(float(row.get("stake") or 0.0) for row in completed)
    wins = sum(1 for row in completed if str(row.get("status") or "").upper() == "WIN")
    open_stake = sum(
        float(row.get("stake") or 0.0)
        for row in strong
        if str(row.get("status") or "PENDING").upper() == "PENDING"
    )
    equity = STRONG_SIGNAL_INITIAL_BANK
    peak = equity
    for row in sorted(completed, key=lambda item: str(item.get("settled_at") or item.get("signal_sent_at") or "")):
        equity += float(row.get("virtual_profit", row.get("profit") or 0.0) or 0.0)
        peak = max(peak, equity)
    current_bank = STRONG_SIGNAL_INITIAL_BANK + total_profit
    drawdown = (peak - current_bank) / peak if peak > 0.0 else 1.0
    return StrongSignalPortfolio(
        initial_bank=STRONG_SIGNAL_INITIAL_BANK,
        current_bank=current_bank,
        total_profit=total_profit,
        total_stake=total_stake,
        roi=total_profit / total_stake if total_stake > 0.0 else 0.0,
        win_rate=wins / len(completed) if completed else 0.0,
        completed_count=len(completed),
        open_stake=open_stake,
        current_drawdown=max(0.0, drawdown),
    )
