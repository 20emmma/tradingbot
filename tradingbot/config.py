"""
config.py

Central configuration. API keys/secrets are read from ENVIRONMENT VARIABLES
only -- never hardcoded in source, never committed to version control.

On your cloud server, you'll set these as actual environment variables
(or a .env file that's git-ignored). This file just defines what's expected
and provides safe validation.

SECURITY NOTES for when you create your API keys:
- Kraken: create a key with "Query Funds" + "Create & Modify Orders"
  permissions ONLY. Do NOT enable "Withdraw Funds". This means even if
  the key leaked, an attacker could trade with your balance but could
  never move money out of the account.
- OANDA: practice account keys and live account keys are separate and
  use different API hosts. Never mix them up.
"""

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()  # reads a .env file in the working directory, if present
except ImportError:
    # python-dotenv not installed -- fine, just means env vars must be
    # set some other way (export, systemd EnvironmentFile, etc.)
    pass


class ConfigError(Exception):
    pass


@dataclass
class Config:
    mode: str                  # "paper" or "live"
    kraken_api_key: str
    kraken_api_secret: str
    oanda_api_token: str
    oanda_account_id: str
    oanda_environment: str     # "practice" or "live"


def load_config() -> Config:
    mode = os.environ.get("BOT_MODE", "paper").lower()
    if mode not in ("paper", "live"):
        raise ConfigError(f"BOT_MODE must be 'paper' or 'live', got: {mode}")

    config = Config(
        mode=mode,
        kraken_api_key=os.environ.get("KRAKEN_API_KEY", ""),
        kraken_api_secret=os.environ.get("KRAKEN_API_SECRET", ""),
        oanda_api_token=os.environ.get("OANDA_API_TOKEN", ""),
        oanda_account_id=os.environ.get("OANDA_ACCOUNT_ID", ""),
        oanda_environment=os.environ.get("OANDA_ENVIRONMENT", "practice"),
    )

    # In paper mode, missing keys is fine for OANDA/Kraken *trading* (no real
    # orders are placed) but we still need keys for KRAKEN's public data
    # endpoints (none required) and OANDA's data endpoints (token IS required
    # even for practice/read-only access).
    if mode == "live":
        if not config.kraken_api_key or not config.kraken_api_secret:
            raise ConfigError("Live mode requires KRAKEN_API_KEY and KRAKEN_API_SECRET")
        if not config.oanda_api_token or not config.oanda_account_id:
            raise ConfigError("Live mode requires OANDA_API_TOKEN and OANDA_ACCOUNT_ID")
        if config.oanda_environment != "live":
            raise ConfigError(
                "Refusing to start: BOT_MODE=live but OANDA_ENVIRONMENT is not 'live'. "
                "This safety check prevents accidentally trading real money against "
                "a practice account mismatch, or vice versa."
            )

    return config
