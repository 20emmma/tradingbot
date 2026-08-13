"""
core/adapters/kraken.py

Kraken REST API adapter.

Public endpoints (OHLC data, current price) need no authentication.
Private endpoints (balance, place order) require API key + secret and
HMAC-SHA512 request signing, per Kraken's documented auth scheme:
https://docs.kraken.com/rest/#section/Authentication

This file implements the standard, publicly-documented signing procedure
exactly as Kraken's own docs specify -- there is nothing unusual here,
it's the same pattern every legitimate Kraken API client uses.
"""

import base64
import hashlib
import hmac
import time
import urllib.parse
from typing import List

import requests

from core.strategy import Candle
from core.adapters.base import MarketAdapter, OrderResult

KRAKEN_API_URL = "https://api.kraken.com"


class KrakenAdapter(MarketAdapter):
    def __init__(self, api_key: str = "", api_secret: str = ""):
        self.api_key = api_key
        self.api_secret = api_secret

    # ---------- Public endpoints (no auth needed) ----------

    def get_candles(self, symbol: str, interval_minutes: int, limit: int) -> List[Candle]:
        """
        symbol example: 'XBTUSD' (Kraken's ticker for BTC/USD)
        interval_minutes must be one of Kraken's supported values:
        1, 5, 15, 30, 60, 240, 1440, 10080, 21600
        """
        resp = requests.get(
            f"{KRAKEN_API_URL}/0/public/OHLC",
            params={"pair": symbol, "interval": interval_minutes},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("error"):
            raise RuntimeError(f"Kraken API error: {data['error']}")

        # Kraken nests the actual OHLC array under a dynamic key matching
        # the resolved pair name -- grab whichever key isn't "last".
        result = data["result"]
        pair_key = next(k for k in result.keys() if k != "last")
        raw_candles = result[pair_key][-limit:]

        candles = []
        for row in raw_candles:
            # Kraken format: [time, open, high, low, close, vwap, volume, count]
            candles.append(Candle(
                timestamp=int(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[6]),
            ))
        return candles

    def get_current_price(self, symbol: str) -> float:
        resp = requests.get(
            f"{KRAKEN_API_URL}/0/public/Ticker",
            params={"pair": symbol},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("error"):
            raise RuntimeError(f"Kraken API error: {data['error']}")
        result = data["result"]
        pair_key = next(iter(result.keys()))
        last_trade_price = float(result[pair_key]["c"][0])
        return last_trade_price

    # ---------- Private endpoints (require signed auth) ----------

    def _sign(self, urlpath: str, data: dict) -> str:
        """Kraken's documented HMAC-SHA512 signing procedure."""
        postdata = urllib.parse.urlencode(data)
        encoded = (str(data["nonce"]) + postdata).encode()
        message = urlpath.encode() + hashlib.sha256(encoded).digest()

        signature = hmac.new(
            base64.b64decode(self.api_secret),
            message,
            hashlib.sha512,
        )
        return base64.b64encode(signature.digest()).decode()

    def _private_request(self, endpoint: str, data: dict = None) -> dict:
        if not self.api_key or not self.api_secret:
            raise RuntimeError(
                "Kraken private API called without credentials. "
                "This should never happen in paper mode -- check your adapter wiring."
            )

        data = data or {}
        data["nonce"] = str(int(time.time() * 1000))
        urlpath = f"/0/private/{endpoint}"

        headers = {
            "API-Key": self.api_key,
            "API-Sign": self._sign(urlpath, data),
        }
        resp = requests.post(f"{KRAKEN_API_URL}{urlpath}", data=data, headers=headers, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        if result.get("error"):
            raise RuntimeError(f"Kraken API error: {result['error']}")
        return result["result"]

    def get_balance(self, currency: str = "ZUSD") -> float:
        result = self._private_request("Balance")
        return float(result.get(currency, 0.0))

    def place_market_order(self, symbol: str, side: str, notional_usd: float) -> OrderResult:
        """
        LIVE MODE ONLY. This places a REAL order using REAL funds.
        Paper mode must never call this -- the paper trading engine
        intercepts before reaching here (see core/paper_engine.py).
        """
        if side not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")

        current_price = self.get_current_price(symbol)
        volume = round(notional_usd / current_price, 8)

        order_data = {
            "pair": symbol,
            "type": side,
            "ordertype": "market",
            "volume": str(volume),
        }
        result = self._private_request("AddOrder", order_data)

        return OrderResult(
            success=True,
            order_id=",".join(result.get("txid", [])),
            side=side,
            requested_qty=volume,
            filled_price=current_price,  # market orders: exact fill price confirmed via QueryOrders afterward
            fee_paid=0.0,  # actual fee available via QueryOrders after fill
            message=result.get("descr", {}).get("order", ""),
        )
