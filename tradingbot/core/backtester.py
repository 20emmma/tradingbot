"""
core/backtester.py

Simulates running the strategy + risk manager over historical candles,
so we can see how it WOULD have performed before risking any money
(paper or real).

Important honesty note: past performance in a backtest is not a promise
of future results. Markets change. This tool is for understanding
strategy *behavior*, not for guaranteeing profit.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from core.strategy import Candle, MovingAverageCrossoverStrategy, Signal
from core.risk import RiskConfig, RiskManager


@dataclass
class Trade:
    entry_time: int
    entry_price: float
    exit_time: Optional[int] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None   # "signal" or "stop_loss"
    pnl: Optional[float] = None


@dataclass
class BacktestResult:
    trades: List[Trade] = field(default_factory=list)
    starting_capital: float = 0.0
    ending_capital: float = 0.0
    halted_days: int = 0

    @property
    def total_return_pct(self) -> float:
        if self.starting_capital == 0:
            return 0.0
        return (self.ending_capital - self.starting_capital) / self.starting_capital * 100

    @property
    def win_rate_pct(self) -> float:
        closed = [t for t in self.trades if t.pnl is not None]
        if not closed:
            return 0.0
        wins = [t for t in closed if t.pnl > 0]
        return len(wins) / len(closed) * 100

    @property
    def num_trades(self) -> int:
        return len([t for t in self.trades if t.pnl is not None])


def run_backtest(
    candles: List[Candle],
    starting_capital: float,
    strategy: Optional[MovingAverageCrossoverStrategy] = None,
    risk_config: Optional[RiskConfig] = None,
) -> BacktestResult:
    strategy = strategy or MovingAverageCrossoverStrategy()
    risk_config = risk_config or RiskConfig()
    strategy.reset()

    first_day = datetime.fromtimestamp(candles[0].timestamp, tz=timezone.utc).date()
    risk = RiskManager(risk_config, starting_capital, first_day)

    result = BacktestResult(starting_capital=starting_capital)

    open_trade: Optional[Trade] = None
    seen_days = set()

    for i in range(1, len(candles) + 1):
        window = candles[:i]
        candle = candles[i - 1]
        day = datetime.fromtimestamp(candle.timestamp, tz=timezone.utc).date()

        was_halted = risk.state.trading_halted_today
        risk.new_day_if_needed(day)
        if was_halted and day not in seen_days:
            result.halted_days += 1
        seen_days.add(day)

        # If we're in a position, check stop-loss first (intra-candle risk check)
        if open_trade is not None:
            sl_price = risk.stop_loss_price(open_trade.entry_price)
            if candle.low <= sl_price:
                notional = risk.position_size()
                qty = notional / open_trade.entry_price
                gross_pnl = (sl_price - open_trade.entry_price) * qty
                fee = risk.apply_fee(notional) * 2  # entry + exit fee
                pnl = gross_pnl - fee

                open_trade.exit_time = candle.timestamp
                open_trade.exit_price = sl_price
                open_trade.exit_reason = "stop_loss"
                open_trade.pnl = pnl
                result.trades.append(open_trade)
                risk.record_trade_result(pnl)
                open_trade = None
                continue  # don't also evaluate a signal on the same candle

        signal = strategy.generate_signal(window)

        if signal == Signal.BUY and open_trade is None and risk.can_open_new_trade():
            open_trade = Trade(entry_time=candle.timestamp, entry_price=candle.close)

        elif signal == Signal.SELL and open_trade is not None:
            notional = risk.position_size()
            qty = notional / open_trade.entry_price
            gross_pnl = (candle.close - open_trade.entry_price) * qty
            fee = risk.apply_fee(notional) * 2
            pnl = gross_pnl - fee

            open_trade.exit_time = candle.timestamp
            open_trade.exit_price = candle.close
            open_trade.exit_reason = "signal"
            open_trade.pnl = pnl
            result.trades.append(open_trade)
            risk.record_trade_result(pnl)
            open_trade = None

    result.ending_capital = risk.state.capital
    return result
