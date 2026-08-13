"""
run_once.py

Does ONE check-and-act cycle, then exits. This is what GitHub Actions
calls on a schedule (e.g. every hour). Unlike main.py's continuous loop,
this process has no memory of previous runs -- all state is loaded from
and saved back to JSON files, which the GitHub Actions workflow commits
to the repo between runs.

Run with:
    MARKET=kraken BOT_MODE=paper python3 run_once.py
    MARKET=oanda BOT_MODE=paper python3 run_once.py
"""

import os
import logging
from datetime import datetime, timezone

from config import load_config, ConfigError
from core.strategy import MovingAverageCrossoverStrategy, Signal
from core.risk import RiskConfig, RiskManager
from core.adapters.kraken import KrakenAdapter
from core.adapters.oanda import OandaAdapter
from core.paper_engine import PaperTradingEngine
from core.notifier import TelegramNotifier
from core.status_writer import StatusWriter
from core.state_store import load_state, save_state

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("tradingbot")

MARKET_SETTINGS = {
    "kraken": {"symbol": "XBTUSD", "interval_minutes": 60, "starting_capital": 10.0},
    "oanda":  {"symbol": "EUR_USD", "interval_minutes": 60, "starting_capital": 10.0},
}


def build_real_adapter(market: str, config):
    if market == "kraken":
        return KrakenAdapter(config.kraken_api_key, config.kraken_api_secret)
    elif market == "oanda":
        return OandaAdapter(config.oanda_api_token, config.oanda_account_id, config.oanda_environment)
    raise ValueError(f"Unknown market: {market}")


def main():
    config = load_config()
    market = os.environ.get("MARKET", "kraken").lower()
    if market not in MARKET_SETTINGS:
        raise ValueError(f"MARKET must be one of {list(MARKET_SETTINGS.keys())}")

    settings = MARKET_SETTINGS[market]
    symbol = settings["symbol"]
    interval_minutes = settings["interval_minutes"]
    today = datetime.now(timezone.utc).date()

    # ---- Load persisted state from the last run ----
    state_path = f"state_{market}.json"
    bot_state = load_state(state_path, settings["starting_capital"], today)

    # Roll over to a new day if needed
    if bot_state.day != today.isoformat():
        bot_state.day = today.isoformat()
        bot_state.daily_pnl = 0.0
        bot_state.trading_halted_today = False

    risk_config = RiskConfig(
        stop_loss_pct=float(os.environ.get("STOP_LOSS_PCT", 0.03)),
        max_daily_loss_pct=float(os.environ.get("MAX_DAILY_LOSS_PCT", 0.05)),
        max_position_pct=float(os.environ.get("MAX_POSITION_PCT", 1.0)),
        fee_pct=float(os.environ.get("FEE_PCT", 0.0026)),
    )
    risk_manager = RiskManager(risk_config, bot_state.starting_capital, today)
    risk_manager.state.capital = bot_state.capital
    risk_manager.state.daily_pnl = bot_state.daily_pnl
    risk_manager.state.trading_halted_today = bot_state.trading_halted_today

    real_adapter = build_real_adapter(market, config)
    engine = PaperTradingEngine(real_adapter, risk_manager, ledger_path=f"paper_ledger_{market}.json") \
        if config.mode == "paper" else real_adapter

    notifier = TelegramNotifier(
        bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
    )
    status_writer = StatusWriter(path=f"status_{market}.json")
    # Preserve recent event history across runs so the dashboard shows a real log, not just one line
    prev_status = {}
    if os.path.exists(f"status_{market}.json"):
        import json
        with open(f"status_{market}.json") as f:
            prev_status = json.load(f)
        status_writer._events = prev_status.get("recent_events", [])

    open_position = bot_state.open_position  # dict or None

    try:
        candles = engine.get_candles(symbol, interval_minutes, limit=100)
        current_price = candles[-1].close
        was_halted_before = risk_manager.state.trading_halted_today

        # Stop-loss check first
        if open_position is not None:
            stop_price = risk_manager.stop_loss_price(open_position["entry_price"])
            if current_price <= stop_price:
                result = engine.place_market_order(symbol, "sell", open_position["notional_usd"])
                pnl = (result.filled_price - open_position["entry_price"]) / open_position["entry_price"] \
                    * open_position["notional_usd"] - result.fee_paid
                risk_manager.record_trade_result(pnl)
                notifier.notify_trade_closed(symbol, result.filled_price, pnl, "stop-loss")
                status_writer.log_event(f"Stop-loss hit: closed {symbol} at ${result.filled_price:.4f}, PnL ${pnl:+.4f}")
                open_position = None

        signal = MovingAverageCrossoverStrategy.stateless_signal(
            candles,
            short_period=int(os.environ.get("SHORT_PERIOD", 9)),
            long_period=int(os.environ.get("LONG_PERIOD", 21)),
        )
        log.info(f"[{market}] Signal: {signal.value} | Price: {current_price} | Capital: ${risk_manager.state.capital:.4f}")

        if signal == Signal.BUY and open_position is None:
            if not risk_manager.can_open_new_trade():
                log.info("Daily loss limit hit — skipping BUY signal today.")
            else:
                notional = risk_manager.position_size()
                result = engine.place_market_order(symbol, "buy", notional)
                open_position = {"side": "buy", "entry_price": result.filled_price, "notional_usd": notional}
                notifier.notify_trade_opened(symbol, result.filled_price, notional)
                status_writer.log_event(f"Opened position: {symbol} at ${result.filled_price:.4f}")

        elif signal == Signal.SELL and open_position is not None:
            result = engine.place_market_order(symbol, "sell", open_position["notional_usd"])
            pnl = (result.filled_price - open_position["entry_price"]) / open_position["entry_price"] \
                * open_position["notional_usd"] - result.fee_paid
            risk_manager.record_trade_result(pnl)
            notifier.notify_trade_closed(symbol, result.filled_price, pnl, "signal")
            status_writer.log_event(f"Closed position via signal: {symbol} at ${result.filled_price:.4f}, PnL ${pnl:+.4f}")
            open_position = None

        if risk_manager.state.trading_halted_today and not was_halted_before:
            notifier.notify_daily_halt(risk_manager.state.daily_pnl)
            status_writer.log_event(f"Daily loss limit hit. Today's PnL: ${risk_manager.state.daily_pnl:+.4f}")

        status_writer.write(
            mode=config.mode, market=market, symbol=symbol, last_signal=signal.value,
            current_price=current_price, capital=risk_manager.state.capital,
            starting_capital=bot_state.starting_capital, daily_pnl=risk_manager.state.daily_pnl,
            trading_halted_today=risk_manager.state.trading_halted_today, open_position=open_position,
        )

    except Exception as e:
        log.error(f"Error during run: {e}", exc_info=True)
        notifier.notify_error(str(e))
        status_writer.log_event(f"ERROR: {e}")
        # Still write a status update so the dashboard reflects that an error
        # occurred, rather than silently going stale. Falls back to the last
        # known price if we never got a fresh one this run.
        last_known_price = prev_status.get("current_price", 0.0)
        try:
            status_writer.write(
                mode=config.mode, market=market, symbol=symbol, last_signal="ERROR",
                current_price=last_known_price, capital=risk_manager.state.capital,
                starting_capital=bot_state.starting_capital, daily_pnl=risk_manager.state.daily_pnl,
                trading_halted_today=risk_manager.state.trading_halted_today, open_position=open_position,
            )
        except Exception:
            pass  # don't let a status-write failure mask the original error
        # Still fall through to save state -- we don't want a transient error
        # to lose track of an open position.

    # ---- Persist state for the next scheduled run ----
    bot_state.capital = risk_manager.state.capital
    bot_state.daily_pnl = risk_manager.state.daily_pnl
    bot_state.trading_halted_today = risk_manager.state.trading_halted_today
    bot_state.open_position = open_position
    save_state(state_path, bot_state)
    log.info(f"[{market}] Run complete. State saved to {state_path}")


if __name__ == "__main__":
    try:
        main()
    except ConfigError as e:
        log.error(f"Configuration error: {e}")
        raise
