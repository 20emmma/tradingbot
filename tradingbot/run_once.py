"""
run_once.py

Does ONE check-and-act cycle, then exits. Called frequently (every ~15 min)
by GitHub Actions, but internally splits its work into two different
cadences:

1. STOP-LOSS CHECK -- runs on every single invocation, using the LIVE
   current price. This is what protects an open position between hourly
   candle closes. If the schedule gets delayed or skipped for a stretch,
   the next run still catches a stop-loss breach as soon as it finally
   runs, using real-time price -- not a stale hourly close.

2. SIGNAL EVALUATION -- only runs when a genuinely NEW hourly candle has
   completed since the last time we checked (tracked via
   last_processed_candle_ts). This keeps the moving-average crossover
   logic clean and noise-free, exactly as if it only ran once per hour --
   frequent checks never cause the strategy to react to a still-forming
   candle.
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


def close_position(engine, notifier, status_writer, risk_manager, symbol, open_position, reason):
    result = engine.place_market_order(symbol, "sell", open_position["notional_usd"])
    pnl = (result.filled_price - open_position["entry_price"]) / open_position["entry_price"] \
        * open_position["notional_usd"] - result.fee_paid
    risk_manager.record_trade_result(pnl)
    notifier.notify_trade_closed(symbol, result.filled_price, pnl, reason)
    status_writer.log_event(f"Closed position via {reason}: {symbol} at ${result.filled_price:.4f}, PnL ${pnl:+.4f}")
    return pnl


def main():
    config = load_config()
    market = os.environ.get("MARKET", "kraken").lower()
    if market not in MARKET_SETTINGS:
        raise ValueError(f"MARKET must be one of {list(MARKET_SETTINGS.keys())}")

    settings = MARKET_SETTINGS[market]
    symbol = settings["symbol"]
    interval_minutes = settings["interval_minutes"]
    today = datetime.now(timezone.utc).date()

    state_path = f"state_{market}.json"
    bot_state = load_state(state_path, settings["starting_capital"], today)

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
    prev_status = {}
    if os.path.exists(f"status_{market}.json"):
        import json
        with open(f"status_{market}.json") as f:
            prev_status = json.load(f)
        status_writer._events = prev_status.get("recent_events", [])
        status_writer._price_history = prev_status.get("price_history", [])

    open_position = bot_state.open_position

    run_count = prev_status.get("run_count", 0) + 1
    heartbeat_every_n_runs = int(os.environ.get("HEARTBEAT_EVERY_N_RUNS", 24))
    if run_count % heartbeat_every_n_runs == 1:
        notifier.send(
            f"\U0001F440 *Heartbeat* — {market} bot is alive and checking.\n"
            f"Capital: ${risk_manager.state.capital:.4f} | Mode: {config.mode.upper()}"
        )

    signal_this_run = Signal.HOLD
    current_price_for_status = prev_status.get("current_price", 0.0)
    live_price_fetched_this_run = False

    try:
        was_halted_before = risk_manager.state.trading_halted_today

        # ---- PART 1: stop-loss check using LIVE price, every single run ----
        if open_position is not None:
            live_price = real_adapter.get_current_price(symbol)
            current_price_for_status = live_price
            live_price_fetched_this_run = True
            stop_price = risk_manager.stop_loss_price(open_position["entry_price"])
            if live_price <= stop_price:
                log.warning(f"[{market}] LIVE stop-loss breach: {live_price} <= {stop_price}")
                close_position(engine, notifier, status_writer, risk_manager,
                                symbol, open_position, "stop-loss")
                open_position = None

        # ---- PART 2: signal evaluation, only if a genuinely new candle exists ----
        candles = engine.get_candles(symbol, interval_minutes, limit=100)
        latest_candle_ts = candles[-1].timestamp
        if not live_price_fetched_this_run:
            current_price_for_status = candles[-1].close
        new_candle_available = latest_candle_ts > bot_state.last_processed_candle_ts

        if new_candle_available:
            signal_this_run = MovingAverageCrossoverStrategy.stateless_signal(
                candles,
                short_period=int(os.environ.get("SHORT_PERIOD", 9)),
                long_period=int(os.environ.get("LONG_PERIOD", 21)),
            )
            bot_state.last_processed_candle_ts = latest_candle_ts
            log.info(f"[{market}] NEW CANDLE -- Signal: {signal_this_run.value} | "
                     f"Price: {current_price_for_status} | Capital: ${risk_manager.state.capital:.4f}")
            status_writer.record_price_point(current_price_for_status, signal_this_run.value)

            if signal_this_run == Signal.BUY and open_position is None:
                if not risk_manager.can_open_new_trade():
                    log.info("Daily loss limit hit — skipping BUY signal today.")
                else:
                    notional = risk_manager.position_size()
                    result = engine.place_market_order(symbol, "buy", notional)
                    open_position = {"side": "buy", "entry_price": result.filled_price, "notional_usd": notional}
                    notifier.notify_trade_opened(symbol, result.filled_price, notional)
                    status_writer.log_event(f"Opened position: {symbol} at ${result.filled_price:.4f}")

            elif signal_this_run == Signal.SELL and open_position is not None:
                close_position(engine, notifier, status_writer, risk_manager,
                                symbol, open_position, "signal")
                open_position = None
        else:
            signal_this_run = Signal(prev_status.get("last_signal", "HOLD")) \
                if prev_status.get("last_signal") in ("BUY", "SELL", "HOLD") else Signal.HOLD
            log.info(f"[{market}] No new candle yet -- stop-loss checked, signal unchanged "
                     f"({signal_this_run.value}) | Price: {current_price_for_status}")

        if risk_manager.state.trading_halted_today and not was_halted_before:
            notifier.notify_daily_halt(risk_manager.state.daily_pnl)
            status_writer.log_event(f"Daily loss limit hit. Today's PnL: ${risk_manager.state.daily_pnl:+.4f}")

        status_writer.write(
            mode=config.mode, market=market, symbol=symbol, last_signal=signal_this_run.value,
            current_price=current_price_for_status, capital=risk_manager.state.capital,
            starting_capital=bot_state.starting_capital, daily_pnl=risk_manager.state.daily_pnl,
            trading_halted_today=risk_manager.state.trading_halted_today, open_position=open_position,
            run_count=run_count,
        )

    except Exception as e:
        log.error(f"Error during run: {e}", exc_info=True)
        notifier.notify_error(str(e))
        status_writer.log_event(f"ERROR: {e}")
        try:
            status_writer.write(
                mode=config.mode, market=market, symbol=symbol, last_signal="ERROR",
                current_price=current_price_for_status, capital=risk_manager.state.capital,
                starting_capital=bot_state.starting_capital, daily_pnl=risk_manager.state.daily_pnl,
                trading_halted_today=risk_manager.state.trading_halted_today, open_position=open_position,
                run_count=run_count,
            )
        except Exception:
            pass

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
