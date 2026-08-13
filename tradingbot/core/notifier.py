"""
core/notifier.py

Telegram push notifications. Optional -- if not configured, the bot just
skips notifications silently (never crashes because Telegram isn't set up).

Setup (also in deploy/TELEGRAM_SETUP.md):
1. Message @BotFather on Telegram, send /newbot, follow prompts
2. It gives you a bot token -> TELEGRAM_BOT_TOKEN
3. Message your new bot anything, then visit:
   https://api.telegram.org/bot<TOKEN>/getUpdates
   to find your chat id -> TELEGRAM_CHAT_ID
"""

import logging
import requests

log = logging.getLogger("tradingbot")

TELEGRAM_API_URL = "https://api.telegram.org"


class TelegramNotifier:
    def __init__(self, bot_token: str = "", chat_id: str = ""):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = bool(bot_token and chat_id)
        if not self.enabled:
            log.info("Telegram notifications not configured -- skipping (this is fine).")

    def send(self, message: str):
        if not self.enabled:
            return
        try:
            resp = requests.post(
                f"{TELEGRAM_API_URL}/bot{self.bot_token}/sendMessage",
                json={"chat_id": self.chat_id, "text": message, "parse_mode": "Markdown"},
                timeout=10,
            )
            if not resp.ok:
                log.warning(f"Telegram notification failed: {resp.status_code} {resp.text}")
        except Exception as e:
            # Never let a notification failure break the trading loop
            log.warning(f"Telegram notification error: {e}")

    # ---- Pre-formatted message helpers for common bot events ----

    def notify_startup(self, mode: str, market: str, symbol: str, capital: float):
        emoji = "\U0001F4DD" if mode == "paper" else "\U0001F6A8"
        self.send(
            f"{emoji} *Bot started*\n"
            f"Mode: {mode.upper()}\n"
            f"Market: {market} ({symbol})\n"
            f"Capital: ${capital:.2f}"
        )

    def notify_trade_opened(self, symbol: str, price: float, notional: float):
        self.send(
            f"\U0001F7E2 *Position opened*\n"
            f"{symbol} @ ${price:.4f}\n"
            f"Size: ${notional:.2f}"
        )

    def notify_trade_closed(self, symbol: str, price: float, pnl: float, reason: str):
        emoji = "\u2705" if pnl >= 0 else "\U0001F534"
        self.send(
            f"{emoji} *Position closed* ({reason})\n"
            f"{symbol} @ ${price:.4f}\n"
            f"PnL: ${pnl:+.4f}"
        )

    def notify_daily_halt(self, daily_pnl: float):
        self.send(
            f"\u26A0\uFE0F *Daily loss limit hit*\n"
            f"Today's PnL: ${daily_pnl:+.4f}\n"
            f"Trading paused until tomorrow."
        )

    def notify_error(self, error_message: str):
        self.send(f"\u274C *Bot error*\n{error_message}")
