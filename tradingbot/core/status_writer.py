"""
core/status_writer.py

Writes the bot's current state to a JSON file after every loop iteration.
The dashboard reads this file to display status -- it never talks to the
bot process directly, keeping the two fully decoupled.
"""

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, List


@dataclass
class BotStatus:
    mode: str
    market: str
    symbol: str
    last_updated: int
    last_signal: str
    current_price: float
    capital: float
    starting_capital: float
    daily_pnl: float
    trading_halted_today: bool
    open_position: Optional[dict]
    recent_events: List[str] = field(default_factory=list)
    price_history: List[dict] = field(default_factory=list)  # [{"t": timestamp, "price": float, "signal": str}]


class StatusWriter:
    def __init__(self, path: str = "status.json", max_events: int = 20, max_history: int = 48):
        self.path = path
        self.max_events = max_events
        self.max_history = max_history  # 48 hourly points = 2 days of history
        self._events: List[str] = []
        self._price_history: List[dict] = []

    def log_event(self, text: str):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        self._events.insert(0, f"[{timestamp}] {text}")
        self._events = self._events[:self.max_events]

    def record_price_point(self, price: float, signal: str):
        self._price_history.append({"t": int(time.time()), "price": price, "signal": signal})
        self._price_history = self._price_history[-self.max_history:]

    def write(self, mode, market, symbol, last_signal, current_price,
              capital, starting_capital, daily_pnl, trading_halted_today,
              open_position):
        status = BotStatus(
            mode=mode, market=market, symbol=symbol, last_updated=int(time.time()),
            last_signal=last_signal, current_price=current_price, capital=capital,
            starting_capital=starting_capital, daily_pnl=daily_pnl,
            trading_halted_today=trading_halted_today, open_position=open_position,
            recent_events=list(self._events), price_history=list(self._price_history),
        )
        with open(self.path, "w") as f:
            json.dump(asdict(status), f, indent=2)
