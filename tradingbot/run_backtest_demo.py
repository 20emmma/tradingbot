import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from data.sample_data import generate_synthetic_candles
from core.strategy import MovingAverageCrossoverStrategy
from core.risk import RiskConfig
from core.backtester import run_backtest

STARTING_CAPITAL = 10.0  # matches the $10 live-trading plan

candles = generate_synthetic_candles(num_candles=1000, start_price=30000.0, volatility=0.012, seed=7)

strategy = MovingAverageCrossoverStrategy(short_period=9, long_period=21)
risk_config = RiskConfig(
    stop_loss_pct=0.03,
    max_daily_loss_pct=0.05,
    max_position_pct=1.0,
    fee_pct=0.0026,
)

result = run_backtest(candles, STARTING_CAPITAL, strategy, risk_config)

print("=" * 50)
print("BACKTEST RESULTS (synthetic demo data)")
print("=" * 50)
print(f"Starting capital:   ${result.starting_capital:.2f}")
print(f"Ending capital:     ${result.ending_capital:.2f}")
print(f"Total return:       {result.total_return_pct:.2f}%")
print(f"Number of trades:   {result.num_trades}")
print(f"Win rate:           {result.win_rate_pct:.1f}%")
print(f"Days trading halted (loss limit hit): {result.halted_days}")
print("=" * 50)

print("\nFirst 5 trades:")
for t in result.trades[:5]:
    print(f"  entry=${t.entry_price:.2f} exit=${t.exit_price:.2f} "
          f"reason={t.exit_reason} pnl=${t.pnl:.4f}")
