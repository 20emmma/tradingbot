"""
backtest_filters.py

Tests whether adding a TREND FILTER to the 9/21 moving-average crossover
reduces the whipsaw losses seen in sideways markets.

A filter only changes whether a BUY crossover is acted on. Exits, stop-loss
and fees are identical for every variation, so differences come only from
which entries get skipped.

Run on two datasets, because one month of data is a small, biased sample:
  A) ~30 days of real HOURLY candles (the recent choppy stretch)
  B) ~120 days of real 4-HOUR candles, same logic with periods in 4h units
     (includes the August rally) -- a robustness check, not the live strategy.

Uses Kraken public data only. Does not touch the live bot or its state.
"""

import sys
from core.strategy import MovingAverageCrossoverStrategy, Signal
from core.adapters.kraken import KrakenAdapter

START_CAPITAL = 10.0
FEE_PCT = 0.0026          # per side, same as the live bot
STOP_PCT = 0.03           # same stop-loss as the live bot
S = MovingAverageCrossoverStrategy._sma


def simulate(candles, short_p, long_p, warmup, trend_n=None, slope_n=0):
    """Long-only simulation. Returns (end_capital, trades, wins, max_drawdown_pct)."""
    capital, pos = START_CAPITAL, None
    trades = wins = 0
    peak, max_dd = capital, 0.0
    closes = []

    def close_trade(exit_price):
        nonlocal capital, pos, trades, wins, peak, max_dd
        gross = capital * (exit_price / pos - 1.0)
        pnl = gross - capital * FEE_PCT * 2          # entry + exit fee
        capital += pnl
        trades += 1
        wins += pnl > 0
        pos = None
        peak = max(peak, capital)
        max_dd = max(max_dd, (peak - capital) / peak * 100)

    for i, c in enumerate(candles):
        closes.append(c.close)
        if i < warmup:
            continue                                  # same start point for every variation
        if pos is not None and c.low <= pos * (1 - STOP_PCT):
            close_trade(pos * (1 - STOP_PCT))         # stop-loss fills at the stop price
            continue
        sig = MovingAverageCrossoverStrategy.stateless_signal(candles[:i + 1], short_p, long_p)
        if sig == Signal.BUY and pos is None:
            ok = True
            if trend_n:
                t = S(closes, trend_n)
                ok = t is not None and c.close > t
            if ok and slope_n > 0:
                # long average must be rising vs slope_n candles ago
                now, before = S(closes, long_p), S(closes[:-slope_n], long_p)
                ok = before is not None and now > before
            if ok:
                pos = c.close
        elif sig == Signal.SELL and pos is not None:
            close_trade(c.close)
    if pos is not None:                               # mark any open trade at the last close
        close_trade(closes[-1])
    return capital, trades, wins, max_dd


def run_dataset(title, candles, short_p, long_p, variants, warmup):
    print(f"\n=== {title} ===")
    print(f"{len(candles)} candles, first {int(warmup)} used as warm-up for every variation")
    bh = candles[-1].close / candles[warmup].close - 1
    print(f"Buy-and-hold over the tested window: {bh*100:+.2f}%\n")
    print(f"{'Variation':<34}{'Return %':>9}{'Trades':>8}{'Win %':>7}{'MaxDD %':>9}{'End $':>9}")
    print("-" * 76)
    rows = []
    for label, kw in variants:
        end, n, w, dd = simulate(candles, short_p, long_p, warmup, **kw)
        ret = (end / START_CAPITAL - 1) * 100
        win = (w / n * 100) if n else 0.0
        rows.append((label, ret))
        print(f"{label:<34}{ret:>8.2f}%{n:>8}{win:>6.1f}%{dd:>8.1f}%{end:>9.3f}")
    return rows


def main():
    adapter = KrakenAdapter()

    h = adapter.get_candles("XBTUSD", 60, 720)[:-1]        # drop the still-forming candle
    run_dataset(
        "A) Real HOURLY candles (live strategy settings)", h, 9, 21,
        [("Baseline 9/21 (what is live)", {}),
         ("+ trend filter: price > SMA50", {"trend_n": 50}),
         ("+ trend filter: price > SMA100", {"trend_n": 100}),
         ("+ trend filter: price > SMA200", {"trend_n": 200}),
         ("+ 21-avg rising (vs 5 candles ago)", {"slope_n": 5}),
         ("+ 21-avg rising (vs 10 candles ago)", {"slope_n": 10}),
         ("+ SMA100 and 21-avg rising (5)", {"trend_n": 100, "slope_n": 5})],
        warmup=200)

    f = adapter.get_candles("XBTUSD", 240, 720)[:-1]       # ~120 days of 4h candles
    run_dataset(
        "B) Real 4-HOUR candles, ~120 days (robustness check)", f, 9, 21,
        [("Baseline 9/21 on 4h", {}),
         ("+ price > SMA50 (4h)", {"trend_n": 50}),
         ("+ price > SMA100 (4h)", {"trend_n": 100}),
         ("+ price > SMA200 (4h)", {"trend_n": 200}),
         ("+ 21-avg rising (vs 5 candles ago)", {"slope_n": 5}),
         ("+ SMA100 and 21-avg rising (5)", {"trend_n": 100, "slope_n": 5})],
        warmup=200)

    print("\nHOW TO READ THIS: only trust a filter that helps in BOTH datasets and "
          "still trades often enough to matter. A filter that wins in A but not in B "
          "is probably fitted to the last month. Max drawdown is measured on closed trades.")


if __name__ == "__main__":
    main()
