"""
main.py

The actual bot loop. This is what runs continuously on your cloud server.

Flow, once per check interval:
1. Fetch latest candles from the adapter (real data, whether paper or live)
2. Feed them to the strategy -> get a signal (BUY/SELL/HOLD)
3. If a position is open, check stop-loss against the latest price
4. Act on the signal, subject to risk manager approval (daily loss limit, etc.)
5. Log what happened
6. Sleep until the next candle is due, repeat

Run with:
    BOT_MODE=paper MARKET=kraken python3 main.py
    BOT_MODE=paper MARKET=oanda python3 main.py

See README.md for full environment variable setup.
"""

import os
import time
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("tradingbot")

# ---- Market-specific settings ----
MARKET_SETTINGS = {
    "kraken": {"symbol": "XBTUSD", "interval_minutes": 60, "starting_capital": 10.0},
    "oanda":  {"symbol": "EUR_USD", "interval_minutes": 60, "starting_capital": 10.0},
}


def build_real_adapter(market: str, config):
    if market == "kraken":
        return KrakenAdapter(config.kraken_api_key, config.kraken_api_secret)
    elif market == "oanda":
        return OandaAdapter(config.oanda_api_token, config.oanda_account_id, config.oanda_environment)
    else:
        raise ValueError(f"Unknown market: {market}")


def run():
    config = load_config()
    market = os.environ.get("MARKET", "kraken").lower()
    if market not in MARKET_SETTINGS:
        raise ValueError(f"MARKET must be one of {list(MARKET_SETTINGS.keys())}")

    settings = MARKET_SETTINGS[market]
    symbol = settings["symbol"]
    interval_minutes = settings["interval_minutes"]

    real_adapter = build_real_adapter(market, config)
    risk_config = RiskConfig(
        stop_loss_pct=float(os.environ.get("STOP_LOSS_PCT", 0.03)),
        max_daily_loss_pct=float(os.environ.get("MAX_DAILY_LOSS_PCT", 0.05)),
        max_position_pct=float(os.environ.get("MAX_POSITION_PCT", 1.0)),
        fee_pct=float(os.environ.get("FEE_PCT", 0.0026)),
    )
    risk_manager = RiskManager(risk_config, settings["starting_capital"], datetime.now(timezone.utc).date())
    strategy = MovingAverageCrossoverStrategy(
        short_period=int(os.environ.get("SHORT_PERIOD", 9)),
        long_period=int(os.environ.get("LONG_PERIOD", 21)),
    )

    if config.mode == "paper":
        engine = PaperTradingEngine(real_adapter, risk_manager, ledger_path=f"paper_ledger_{market}.json")
        log.info(f"Starting in PAPER mode on {market} ({symbol}). No real money is at risk.")
    else:
        engine = real_adapter
        log.warning(
            f"Starting in LIVE mode on {market} ({symbol}). "
            f"REAL MONEY IS AT RISK. Starting capital tracked: ${settings['starting_capital']}"
        )

    notifier = TelegramNotifier(
        bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        chat_id=os.environ.get("TELEGRAM_CHAT_ID", ""),
    )
    status_writer = StatusWriter(path=f"status_{market}.json")
    notifier.notify_startup(config.mode, market, symbol, settings["starting_capital"])
    status_writer.log_event(f"Bot started in {config.mode.upper()} mode on {market} ({symbol})")

    open_position = None  # {"side": "buy", "entry_price": float, "notional_usd": float}

    log.info(f"Strategy: MA({strategy.short_period}/{strategy.long_period}) | "
             f"Stop-loss: {risk_config.stop_loss_pct*100:.1f}% | "
             f"Max daily loss: {risk_config.max_daily_loss_pct*100:.1f}%")

    while True:
        try:
            today = datetime.now(timezone.utc).date()
            risk_manager.new_day_if_needed(today)

            candles = engine.get_candles(symbol, interval_minutes, limit=max(50, strategy.long_period + 5))
            current_price = candles[-1].close

            was_halted_before = risk_manager.state.trading_halted_today

            # Check stop-loss first if we're in a position
            if open_position is not None:
                stop_price = risk_manager.stop_loss_price(open_position["entry_price"])
                if current_price <= stop_price:
                    log.warning(f"Stop-loss triggered at {current_price} (entry was {open_position['entry_price']})")
                    result = engine.place_market_order(symbol, "sell", open_position["notional_usd"])
                    pnl = (result.filled_price - open_position["entry_price"]) / open_position["entry_price"] \
                        * open_position["notional_usd"] - result.fee_paid
                    risk_manager.record_trade_result(pnl)
                    log.info(f"Position closed via stop-loss. PnL: ${pnl:.4f}")
                    notifier.notify_trade_closed(symbol, result.filled_price, pnl, "stop-loss")
                    status_writer.log_event(f"Stop-loss hit: closed {symbol} at ${result.filled_price:.4f}, PnL ${pnl:+.4f}")
                    open_position = None

            signal = strategy.generate_signal(candles)
            log.info(f"Signal: {signal.value} | Price: {current_price} | Capital: ${risk_manager.state.capital:.4f}")

            if signal == Signal.BUY and open_position is None:
                if not risk_manager.can_open_new_trade():
                    log.info("Daily loss limit hit — skipping BUY signal today.")
                else:
                    notional = risk_manager.position_size()
                    result = engine.place_market_order(symbol, "buy", notional)
                    open_position = {
                        "side": "buy",
                        "entry_price": result.filled_price,
                        "notional_usd": notional,
                    }
                    log.info(f"Opened position: {result}")
                    notifier.notify_trade_opened(symbol, result.filled_price, notional)
                    status_writer.log_event(f"Opened position: {symbol} at ${result.filled_price:.4f}")

            elif signal == Signal.SELL and open_position is not None:
                result = engine.place_market_order(symbol, "sell", open_position["notional_usd"])
                pnl = (result.filled_price - open_position["entry_price"]) / open_position["entry_price"] \
                    * open_position["notional_usd"] - result.fee_paid
                risk_manager.record_trade_result(pnl)
                log.info(f"Closed position via signal. PnL: ${pnl:.4f}")
                notifier.notify_trade_closed(symbol, result.filled_price, pnl, "signal")
                status_writer.log_event(f"Closed position via signal: {symbol} at ${result.filled_price:.4f}, PnL ${pnl:+.4f}")
                open_position = None

            # Notify once, right when the daily halt newly triggers (not every loop after)
            if risk_manager.state.trading_halted_today and not was_halted_before:
                notifier.notify_daily_halt(risk_manager.state.daily_pnl)
                status_writer.log_event(f"Daily loss limit hit. Today's PnL: ${risk_manager.state.daily_pnl:+.4f}")

            status_writer.write(
                mode=config.mode,
                market=market,
                symbol=symbol,
                last_signal=signal.value,
                current_price=current_price,
                capital=risk_manager.state.capital,
                starting_capital=settings["starting_capital"],
                daily_pnl=risk_manager.state.daily_pnl,
                trading_halted_today=risk_manager.state.trading_halted_today,
                open_position=open_position,
            )

        except Exception as e:
            log.error(f"Error in trading loop: {e}", exc_info=True)
            notifier.notify_error(str(e))
            status_writer.log_event(f"ERROR: {e}")
            # Deliberately does NOT crash the whole bot on a transient error
            # (e.g. a dropped API call) -- it logs and tries again next cycle.

        sleep_seconds = interval_minutes * 60
        log.info(f"Sleeping {sleep_seconds}s until next check...")
        time.sleep(sleep_seconds)


if __name__ == "__main__":
    try:
        run()
    except ConfigError as e:
        log.error(f"Configuration error: {e}")
    except KeyboardInterrupt:
        log.info("Bot stopped by user.")
