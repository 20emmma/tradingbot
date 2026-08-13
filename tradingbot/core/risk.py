"""
core/risk.py

Safety rails that apply REGARDLESS of what the strategy says.
These exist because a strategy signal ("BUY") should never be followed
blindly -- risk management is what keeps one bad trade or one bad day
from doing serious damage, especially with a small account.

Three guardrails, on by default:
1. Stop-loss per trade: auto-exit if a position drops more than X%.
2. Max daily loss: stop opening new trades once today's losses hit a cap.
3. Max position size: never risk more than a set % of capital on one trade.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class RiskConfig:
    stop_loss_pct: float = 0.03        # exit a position if it drops 3%
    max_daily_loss_pct: float = 0.05   # stop trading for the day after -5%
    max_position_pct: float = 1.0      # fraction of capital usable per trade (1.0 = 100%, small accounts often go full-in)
    fee_pct: float = 0.0026            # example: Kraken taker fee ~0.26%


@dataclass
class RiskState:
    """Tracks running state that risk decisions depend on."""
    starting_capital: float
    capital: float
    day: date
    daily_pnl: float = 0.0
    trading_halted_today: bool = False


class RiskManager:
    def __init__(self, config: RiskConfig, starting_capital: float, today: date):
        self.config = config
        self.state = RiskState(
            starting_capital=starting_capital,
            capital=starting_capital,
            day=today,
        )

    def new_day_if_needed(self, current_day: date):
        """Reset daily counters when a new day starts."""
        if current_day != self.state.day:
            self.state.day = current_day
            self.state.daily_pnl = 0.0
            self.state.trading_halted_today = False

    def can_open_new_trade(self) -> bool:
        """False if today's loss limit has been hit."""
        return not self.state.trading_halted_today

    def position_size(self) -> float:
        """How much capital to risk on the next trade."""
        return self.state.capital * self.config.max_position_pct

    def stop_loss_price(self, entry_price: float) -> float:
        """Price at which a long position should be force-closed."""
        return entry_price * (1 - self.config.stop_loss_pct)

    def apply_fee(self, notional: float) -> float:
        """Fee charged on a trade of this notional size."""
        return notional * self.config.fee_pct

    def record_trade_result(self, pnl: float):
        """Update capital and daily P&L after a trade closes."""
        self.state.capital += pnl
        self.state.daily_pnl += pnl

        loss_limit = -abs(self.config.max_daily_loss_pct) * self.state.starting_capital
        if self.state.daily_pnl <= loss_limit:
            self.state.trading_halted_today = True
