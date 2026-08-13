"""
core/adapters/base.py

Every market adapter (Kraken, OANDA, future additions) implements this
same interface. This is what lets the strategy/backtester/paper-trading/
live-trading code stay identical regardless of which market it's pointed at.

An adapter's job is ONLY to:
1. Fetch candle data in our common Candle format
2. Report account balance
3. Place/report on orders

It should NOT contain strategy logic, risk logic, or decision-making.
Keeping that separation is what makes paper mode a one-line switch.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List

from core.strategy import Candle


@dataclass
class OrderResult:
    success: bool
    order_id: str
    side: str            # "buy" or "sell"
    requested_qty: float
    filled_price: float
    fee_paid: float
    message: str = ""


class MarketAdapter(ABC):
    """Common interface for any market data/execution source."""

    @abstractmethod
    def get_candles(self, symbol: str, interval_minutes: int, limit: int) -> List[Candle]:
        """Fetch the most recent `limit` candles for `symbol`."""
        raise NotImplementedError

    @abstractmethod
    def get_current_price(self, symbol: str) -> float:
        """Latest traded/mid price for `symbol`."""
        raise NotImplementedError

    @abstractmethod
    def get_balance(self, currency: str) -> float:
        """Available balance in `currency` (e.g. 'USD', 'ZUSD')."""
        raise NotImplementedError

    @abstractmethod
    def place_market_order(self, symbol: str, side: str, notional_usd: float) -> OrderResult:
        """
        Place a market order sized in USD notional (not units), since that's
        how the risk manager thinks about position sizing.
        side: "buy" or "sell"
        """
        raise NotImplementedError
