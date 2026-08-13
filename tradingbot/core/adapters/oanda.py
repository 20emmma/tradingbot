"""
core/adapters/oanda.py

OANDA v20 REST API adapter, for forex.

OANDA cleanly separates practice and live with different hostnames --
this is a good safety property (much harder to accidentally hit live
when you meant practice, compared to exchanges that use one host with
a mode flag).

Docs: https://developer.oanda.com/rest-live-v20/introduction/
"""

from typing import List

import requests

from core.strategy import Candle
from core.adapters.base import MarketAdapter, OrderResult

OANDA_HOSTS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live": "https://api-fxtrade.oanda.com",
}

# Maps our common interval-in-minutes to OANDA's granularity codes.
GRANULARITY_MAP = {
    1: "M1", 5: "M5", 15: "M15", 30: "M30",
    60: "H1", 240: "H4", 1440: "D",
}


class OandaAdapter(MarketAdapter):
    def __init__(self, api_token: str, account_id: str, environment: str = "practice"):
        if environment not in OANDA_HOSTS:
            raise ValueError("environment must be 'practice' or 'live'")
        self.api_token = api_token
        self.account_id = account_id
        self.base_url = OANDA_HOSTS[environment]
        self.environment = environment

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
        }

    def get_candles(self, symbol: str, interval_minutes: int, limit: int) -> List[Candle]:
        """symbol example: 'EUR_USD'"""
        granularity = GRANULARITY_MAP.get(interval_minutes)
        if granularity is None:
            raise ValueError(f"Unsupported interval_minutes: {interval_minutes}")

        resp = requests.get(
            f"{self.base_url}/v3/instruments/{symbol}/candles",
            headers=self._headers(),
            params={"granularity": granularity, "count": limit, "price": "M"},  # mid prices
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        candles = []
        for c in data.get("candles", []):
            if not c.get("complete", True):
                continue  # skip the currently-forming candle
            mid = c["mid"]
            candles.append(Candle(
                timestamp=int(__import__("datetime").datetime.fromisoformat(
                    c["time"].replace("Z", "+00:00")
                ).timestamp()),
                open=float(mid["o"]),
                high=float(mid["h"]),
                low=float(mid["l"]),
                close=float(mid["c"]),
                volume=float(c.get("volume", 0)),
            ))
        return candles

    def get_current_price(self, symbol: str) -> float:
        resp = requests.get(
            f"{self.base_url}/v3/accounts/{self.account_id}/pricing",
            headers=self._headers(),
            params={"instruments": symbol},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        prices = data["prices"][0]
        bid = float(prices["bids"][0]["price"])
        ask = float(prices["asks"][0]["price"])
        return (bid + ask) / 2

    def get_balance(self, currency: str = "USD") -> float:
        resp = requests.get(
            f"{self.base_url}/v3/accounts/{self.account_id}/summary",
            headers=self._headers(),
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return float(data["account"]["balance"])

    def place_market_order(self, symbol: str, side: str, notional_usd: float) -> OrderResult:
        """
        LIVE MODE ONLY. This places a REAL order using REAL funds.
        Paper mode must never call this -- the paper trading engine
        intercepts before reaching here.

        Note: OANDA order 'units' are positive for buy, negative for sell.
        notional_usd is converted to units using current price as an approximation
        (fine for the very small position sizes this bot is designed for).
        """
        if side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")

        current_price = self.get_current_price(symbol)
        units = int(notional_usd / current_price)
        if units < 1:
            units = 1  # OANDA requires at least 1 unit
        if side == "sell":
            units = -units

        order_payload = {
            "order": {
                "type": "MARKET",
                "instrument": symbol,
                "units": str(units),
            }
        }
        resp = requests.post(
            f"{self.base_url}/v3/accounts/{self.account_id}/orders",
            headers=self._headers(),
            json=order_payload,
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        fill = data.get("orderFillTransaction", {})
        return OrderResult(
            success="orderFillTransaction" in data,
            order_id=fill.get("id", ""),
            side=side,
            requested_qty=abs(units),
            filled_price=float(fill.get("price", current_price)),
            fee_paid=0.0,  # OANDA folds cost into spread, not a separate fee line
            message=data.get("orderCreateTransaction", {}).get("type", ""),
        )
