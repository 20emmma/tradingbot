"""
data/sample_data.py

IMPORTANT: This generates SYNTHETIC price data for demo/testing purposes only.
It is NOT real historical market data. It's built to have realistic-ish
volatility and occasional trends so the backtester has something meaningful
to chew on, but you should NOT draw real conclusions about actual BTC/USD
or EUR/USD performance from it.

When the bot is deployed to your cloud server (with real internet access),
it will pull ACTUAL historical data from Kraken's / OANDA's API for
backtesting, and this synthetic generator won't be used at all.
"""

import random
import time
from typing import List

from core.strategy import Candle


def generate_synthetic_candles(
    num_candles: int = 500,
    start_price: float = 30000.0,
    candle_interval_seconds: int = 3600,  # 1 hour candles
    volatility: float = 0.01,
    seed: int = 42,
) -> List[Candle]:
    """
    Random-walk price generator with occasional short "trend" phases,
    so a trend-following strategy has something to react to (not just noise).
    """
    rng = random.Random(seed)
    candles = []
    price = start_price
    now = int(time.time())
    start_ts = now - num_candles * candle_interval_seconds

    trend_bias = 0.0
    trend_counter = 0

    for i in range(num_candles):
        # Occasionally start a new trend phase (up or down) for realism
        if trend_counter <= 0:
            trend_bias = rng.choice([-1, 0, 0, 1]) * volatility * 0.5
            trend_counter = rng.randint(10, 40)
        trend_counter -= 1

        change_pct = rng.gauss(trend_bias, volatility)
        open_price = price
        close_price = max(0.01, price * (1 + change_pct))
        high_price = max(open_price, close_price) * (1 + abs(rng.gauss(0, volatility * 0.3)))
        low_price = min(open_price, close_price) * (1 - abs(rng.gauss(0, volatility * 0.3)))
        volume = abs(rng.gauss(100, 30))

        ts = start_ts + i * candle_interval_seconds
        candles.append(Candle(
            timestamp=ts,
            open=round(open_price, 2),
            high=round(high_price, 2),
            low=round(low_price, 2),
            close=round(close_price, 2),
            volume=round(volume, 2),
        ))
        price = close_price

    return candles
