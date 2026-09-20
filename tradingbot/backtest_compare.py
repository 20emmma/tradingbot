"""
backtest_compare.py

Fetches REAL recent Kraken hourly candle history (up to 720 hours / ~30 days,
Kraken's public API limit) and backtests several parameter variations
against it, printing a comparison table.

This is a one-off analysis tool, not part of the live bot -- run manually
via the "Backtest Comparison" GitHub Actions workflow (workflow_dispatch
only, no schedule), since Kraken's API isn't reachable from every
environment.
"""

import sys
from core.adapters.kraken import KrakenAdapter
from core.strategy import MovingAverageCrossoverStrategy
from core.risk import RiskConfig
from core.backtester import run_backtest

STARTING_CAPITAL = 10.0

VARIATIONS = [
    ("Current (9/21, 3% SL)",        9,  21, 0.03),
    ("Wider stop (9/21, 5% SL)",     9,  21, 0.05),
    ("Classic MACD-ish (12/26, 3%)", 12, 26, 0.03),
    ("Classic MACD-ish (12/26, 5%)", 12, 26, 0.05),
    ("Faster (5/13, 3% SL)",         5,  13, 0.03),
    ("Slower (15/35, 3% SL)",        15, 35, 0.03),
]


def main():
    print("Fetching real Kraken hourly candle history (XBT/USD)...")
    adapter = KrakenAdapter()
    candles = adapter.get_candles("XBTUSD", interval_minutes=60, limit=720)
    print(f"Fetched {len(candles)} real hourly candles "
          f"({candles[0].timestamp} to {candles[-1].timestamp})\n")

    if len(candles) < 50:
        print("ERROR: Not enough candle data returned to backtest meaningfully.")
        sys.exit(1)

    results = []
    for label, short_p, long_p, sl_pct in VARIATIONS:
        strategy = MovingAverageCrossoverStrategy(short_period=short_p, long_period=long_p)
        risk_config = RiskConfig(stop_loss_pct=sl_pct, max_daily_loss_pct=0.05,
                                   max_position_pct=1.0, fee_pct=0.0026)
        result = run_backtest(candles, STARTING_CAPITAL, strategy, risk_config)
        results.append((label, result))

    print(f"{'Variation':<32} {'Return %':>10} {'Trades':>8} {'Win %':>8} {'End $':>8}")
    print("-" * 70)
    for label, result in results:
        print(f"{label:<32} {result.total_return_pct:>9.2f}% {result.num_trades:>8} "
              f"{result.win_rate_pct:>7.1f}% {result.ending_capital:>8.4f}")

    best = max(results, key=lambda r: r[1].total_return_pct)
    print(f"\nBest performer over this real ~30-day window: {best[0]} "
          f"({best[1].total_return_pct:+.2f}%)")
    print("\nIMPORTANT: This is one recent ~30-day window on ONE asset. "
          "A single best result here is NOT a guarantee it'll keep winning -- "
          "treat this as exploratory, not a final decision.")


if __name__ == "__main__":
    main()
