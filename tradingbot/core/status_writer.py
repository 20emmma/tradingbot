"""
core/status_writer.py

Writes the bot's current state to a JSON file after every loop iteration.
The dashboard (a separate small web app) reads this file to display
status -- it never talks to the bot process directly, which keeps the
two completely decoupled (dashboard can be restarted, redeployed, or
crash without affecting the actual trading bot).
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


class StatusWriter:
    def __init__(self, path: str = "status.json", max_events: int = 20):
        self.path = path
        self.max_events = max_events
        self._events: List[str] = []

    def log_event(self, text: str):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        self._events.insert(0, f"[{timestamp}] {text}")
        self._events = self._events[:self.max_events]

    def write(self, mode, market, symbol, last_signal, current_price,
              capital, starting_capital, daily_pnl, trading_halted_today,
              open_position):
        status = BotStatus(
            mode=mode,
            market=market,
            symbol=symbol,
            last_updated=int(time.time()),
            last_signal=last_signal,
            current_price=current_price,
            capital=capital,
            starting_capital=starting_capital,
            daily_pnl=daily_pnl,
            trading_halted_today=trading_halted_today,
            open_position=open_position,
            recent_events=list(self._events),
        )
        with open(self.path, "w") as f:
            json.dump(asdict(status), f, indent=2)
