"""
core/state_store.py

Since GitHub Actions gives you a fresh, empty filesystem on every scheduled
run, the bot has no memory between runs unless we explicitly save and
reload it. This module handles that: state is saved to a JSON file, which
the GitHub Actions workflow commits back to the repo after each run, and
reloads at the start of the next run.

This is the key piece that makes "run once per hour on a schedule" behave
identically to "run continuously and check once per hour" from a trading
logic standpoint.
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
    day: str                    # ISO date string, e.g. "2026-08-12"
    daily_pnl: float
    trading_halted_today: bool
    open_position: Optional[dict]  # {"side", "entry_price", "notional_usd"} or None


def load_state(path: str, starting_capital: float, today: date) -> BotState:
    """Load saved state, or create a fresh one if this is the first-ever run."""
    if os.path.exists(path):
        with open(path) as f:
            raw = json.load(f)
        return BotState(**raw)

    return BotState(
        capital=starting_capital,
        starting_capital=starting_capital,
        day=today.isoformat(),
        daily_pnl=0.0,
        trading_halted_today=False,
        open_position=None,
    )


def save_state(path: str, state: BotState):
    with open(path, "w") as f:
        json.dump(asdict(state), f, indent=2)
