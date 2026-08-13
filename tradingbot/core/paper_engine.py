"""
core/paper_engine.py

Paper trading engine.

KEY IDEA: this does NOT reimplement market logic. It wraps a REAL adapter
(KrakenAdapter or OandaAdapter) so that:
  - get_candles() / get_current_price()  -> pass straight through to the real adapter
    (paper trading uses REAL live market data, just simulated money)
  - place_market_order()                 -> intercepted, simulated locally,
    NEVER reaches the real exchange/broker

This means the exact same strategy + risk manager code runs identically in
paper and live mode. Switching modes later means swapping which engine
wraps the adapter -- not rewriting any trading logic.
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import List

from core.strategy import Candle
from core.adapters.base import MarketAdapter, OrderResult
from core.risk import RiskManager


@dataclass
class PaperLedgerEntry:
    timestamp: int
    symbol: str
    side: str
    notional_usd: float
    price: float
    fee: float
    balance_after: float


class PaperTradingEngine:
    """
    Drop-in stand-in for a MarketAdapter's order execution, backed by a
    real adapter for market data. Persists its ledger to disk so you can
    close your laptop/SSH session and the bot (running on your server)
    keeps its state.
    """

    def __init__(self, real_adapter: MarketAdapter, risk_manager: RiskManager,
                 ledger_path: str = "paper_ledger.json"):
        self.real_adapter = real_adapter
        self.risk_manager = risk_manager
        self.ledger_path = ledger_path
        self.ledger: List[PaperLedgerEntry] = []
        self.open_position = None  # dict: {symbol, side, qty, entry_price}
        self._load_ledger()

    # ---- market data: pass straight through to the real adapter ----

    def get_candles(self, symbol: str, interval_minutes: int, limit: int) -> List[Candle]:
        return self.real_adapter.get_candles(symbol, interval_minutes, limit)

    def get_current_price(self, symbol: str) -> float:
        return self.real_adapter.get_current_price(symbol)

    def get_balance(self, currency: str = "USD") -> float:
        return self.risk_manager.state.capital

    # ---- order execution: simulated, never touches the real account ----

    def place_market_order(self, symbol: str, side: str, notional_usd: float) -> OrderResult:
        price = self.real_adapter.get_current_price(symbol)  # real market price, simulated fill
        fee = self.risk_manager.apply_fee(notional_usd)
        qty = notional_usd / price

        entry = PaperLedgerEntry(
            timestamp=int(time.time()),
            symbol=symbol,
            side=side,
            notional_usd=notional_usd,
            price=price,
            fee=fee,
            balance_after=self.risk_manager.state.capital,  # updated by caller via record_trade_result
        )
        self.ledger.append(entry)
        self._save_ledger()

        return OrderResult(
            success=True,
            order_id=f"PAPER-{entry.timestamp}",
            side=side,
            requested_qty=qty,
            filled_price=price,
            fee_paid=fee,
            message="Simulated fill (paper mode) — no real order was placed.",
        )

    # ---- persistence, so the bot survives restarts ----

    def _save_ledger(self):
        with open(self.ledger_path, "w") as f:
            json.dump([entry.__dict__ for entry in self.ledger], f, indent=2)

    def _load_ledger(self):
        if os.path.exists(self.ledger_path):
            with open(self.ledger_path) as f:
                raw = json.load(f)
            self.ledger = [PaperLedgerEntry(**row) for row in raw]
