"""
core/state_store.py

Persists bot state between runs (needed since GitHub Actions gives a fresh
filesystem every run). Saved to JSON, committed back to the repo.
"""

import json
import os
from dataclasses import dataclass, asdict
from datetime import date
from typing import Optional


@dataclass
class BotState:
    capital: float
    starting_capital: float
    day: str
    daily_pnl: float
    trading_halted_today: bool
    open_position: Optional[dict]
    last_processed_candle_ts: int = 0


def load_state(path: str, starting_capital: float, today: date) -> BotState:
    if os.path.exists(path):
        with open(path) as f:
            raw = json.load(f)
        raw.setdefault("last_processed_candle_ts", 0)
        return BotState(**raw)

    return BotState(
        capital=starting_capital,
        starting_capital=starting_capital,
        day=today.isoformat(),
        daily_pnl=0.0,
        trading_halted_today=False,
        open_position=None,
        last_processed_candle_ts=0,
    )


def save_state(path: str, state: BotState):
    with open(path, "w") as f:
        json.dump(asdict(state), f, indent=2)
