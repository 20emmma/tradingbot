"""
core/strategy.py

Moving Average Crossover strategy.

This is intentionally simple and well-understood:
- Track a SHORT-period moving average and a LONG-period moving average.
- When SHORT crosses ABOVE LONG  -> bullish signal -> BUY
- When SHORT crosses BELOW LONG  -> bearish signal -> SELL
- Otherwise -> HOLD (no action)

This logic is market-agnostic: it works on any list of OHLCV candles,
whether they come from a crypto exchange or a forex broker. Market-specific
details (order sizing, minimum trade size, fees) live in the adapters,
not here.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class Signal(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class Candle:
    timestamp: int      # unix timestamp (seconds)
    open: float
    high: float
    low: float
    close: float
    volume: float


class MovingAverageCrossoverStrategy:
    """
    Beginner-friendly trend-following strategy.

    short_period: number of candles for the fast-moving average (default 9)
    long_period:  number of candles for the slow-moving average (default 21)

    These defaults are common starting points, not guarantees of performance.
    Different assets / timeframes may need different tuning -- that's exactly
    what the backtester is for.
    """

    def __init__(self, short_period: int = 9, long_period: int = 21):
        if short_period >= long_period:
            raise ValueError("short_period must be smaller than long_period")
        self.short_period = short_period
        self.long_period = long_period

        # Internal state so we can detect a *crossover* (a change in relationship),
        # not just "short is above long" on every single candle.
        self._prev_short: Optional[float] = None
        self._prev_long: Optional[float] = None

    @staticmethod
    def _sma(values: List[float], period: int) -> Optional[float]:
        """Simple moving average of the last `period` values."""
        if len(values) < period:
            return None
        return sum(values[-period:]) / period

    def generate_signal(self, candles: List[Candle]) -> Signal:
        """
        Given the full candle history up to "now" (most recent candle last),
        return the current signal: BUY, SELL, or HOLD.

        Call this once per new candle in live/paper trading, or in a loop
        for backtesting.
        """
        closes = [c.close for c in candles]

        short_ma = self._sma(closes, self.short_period)
        long_ma = self._sma(closes, self.long_period)

        # Not enough data yet to compute both averages.
        if short_ma is None or long_ma is None:
            return Signal.HOLD

        signal = Signal.HOLD

        if self._prev_short is not None and self._prev_long is not None:
            crossed_up = self._prev_short <= self._prev_long and short_ma > long_ma
            crossed_down = self._prev_short >= self._prev_long and short_ma < long_ma

            if crossed_up:
                signal = Signal.BUY
            elif crossed_down:
                signal = Signal.SELL

        self._prev_short = short_ma
        self._prev_long = long_ma

        return signal

    def reset(self):
        """Clear internal state (e.g. when starting a fresh backtest run)."""
        self._prev_short = None
        self._prev_long = None

    @staticmethod
    def stateless_signal(candles: List[Candle], short_period: int = 9, long_period: int = 21) -> Signal:
        """
        Same crossover logic as generate_signal(), but with NO dependency on
        object state from previous calls. Needed for scheduled/serverless
        execution (e.g. GitHub Actions), where each run is a fresh process
        with no memory of the previous run's moving averages.

        Works by comparing the short/long MA relationship at the most recent
        candle against the relationship one candle earlier -- if it flipped,
        that's the crossover. Requires at least long_period + 1 candles.
        """
        closes = [c.close for c in candles]
        if len(closes) < long_period + 1:
            return Signal.HOLD

        short_now = MovingAverageCrossoverStrategy._sma(closes, short_period)
        long_now = MovingAverageCrossoverStrategy._sma(closes, long_period)
        short_prev = MovingAverageCrossoverStrategy._sma(closes[:-1], short_period)
        long_prev = MovingAverageCrossoverStrategy._sma(closes[:-1], long_period)

        if None in (short_now, long_now, short_prev, long_prev):
            return Signal.HOLD

        crossed_up = short_prev <= long_prev and short_now > long_now
        crossed_down = short_prev >= long_prev and short_now < long_now

        if crossed_up:
            return Signal.BUY
        elif crossed_down:
            return Signal.SELL
        return Signal.HOLD
