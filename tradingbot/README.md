# Beginner Trading Bot — Crypto (Kraken) + Forex (OANDA)

## ⚠️ Read this first

This bot trades real strategies (moving average crossover) with real risk
controls, but it is **not a guarantee of profit**. It's built to run safely
and transparently at very small capital ($10 to start), starting in
**paper mode** (simulated money, real market data) before any real funds
are involved.

You are not required to go live. Paper mode alone is a legitimate way to
learn how markets and this strategy behave.

## What's built so far

| File | Purpose |
|---|---|
| `core/strategy.py` | Moving average crossover signal logic (market-agnostic) |
| `core/risk.py` | Stop-loss, daily loss limit, position sizing |
| `core/backtester.py` | Simulates the strategy over historical data |
| `core/adapters/base.py` | Common interface all markets implement |
| `core/adapters/kraken.py` | Kraken REST API adapter (crypto) |
| `core/adapters/oanda.py` | OANDA v20 REST API adapter (forex) |
| `core/paper_engine.py` | Wraps a real adapter; simulates order fills instead of placing real orders |
| `config.py` | Loads settings from environment variables; has a live-mode safety check |
| `main.py` | The actual bot loop |
| `data/sample_data.py` | **Sandbox-only** synthetic data generator, not used in real deployment |

## Hosting

This bot runs on **GitHub Actions (scheduled hourly) + Render (free dashboard)**
— no credit card required anywhere. See `deploy/GITHUB_ACTIONS_SETUP.md`
for full setup. (`deploy/ORACLE_CLOUD_SETUP.md` is kept for reference if
you later want a traditional always-on server instead — functionally
equivalent for this hourly strategy, just needs a card.)

## Setup (local testing before deploying)

```bash
git clone <wherever you host this> tradingbot
cd tradingbot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Environment variables

Create a `.env` file (and make sure it's in `.gitignore` — never commit
real keys):

```bash
BOT_MODE=paper              # "paper" or "live"
MARKET=kraken                # "kraken" or "oanda"

# Kraken (only required for LIVE mode; paper mode reads public data with no key)
KRAKEN_API_KEY=
KRAKEN_API_SECRET=

# OANDA (token required even in paper mode, since OANDA's data endpoints need auth)
OANDA_API_TOKEN=
OANDA_ACCOUNT_ID=
OANDA_ENVIRONMENT=practice   # "practice" or "live" -- must match BOT_MODE or the bot refuses to start

# Strategy tuning (optional, these are the defaults)
SHORT_PERIOD=9
LONG_PERIOD=21
STOP_LOSS_PCT=0.03
MAX_DAILY_LOSS_PCT=0.05
MAX_POSITION_PCT=1.0
FEE_PCT=0.0026
```

Load it before running, e.g. with `export $(cat .env | xargs)` or a tool
like `python-dotenv`.

### Getting API credentials

**Kraken** (only needed once you go live):
1. Log into Kraken → Settings → API → Generate New Key
2. Enable ONLY: "Query Funds", "Create & Modify Orders"
3. Do **NOT** enable "Withdraw Funds" — this means even a leaked key
   can't be used to steal your money, only to trade with it
4. Copy the key + secret into your `.env`

**OANDA**:
1. Sign up at oanda.com — you'll get a free practice account automatically
2. Practice account → My Account → Manage API Access → generate a token
3. For paper trading, use your practice token + `OANDA_ENVIRONMENT=practice`
4. Only generate a **live** token once you're ready to go live with real funds

### Running

```bash
python3 main.py
```

It'll run continuously, checking for new candles and logging every decision.
Use `screen`, `tmux`, or a `systemd` service to keep it running after you
disconnect from the server (I can help set this up next).

## Switching from paper to live

Two things change, nothing else:
```bash
BOT_MODE=live
OANDA_ENVIRONMENT=live   # if trading OANDA
```
Plus you'll need real (not practice) API credentials. The strategy, risk
rules, and bot logic are byte-for-byte identical — that's the point.

## Known limitations / honesty notes

- This has **not yet been tested against live Kraken/OANDA data from a
  GitHub Actions runner specifically**. A local sandbox test hit a `403
  Forbidden` from Kraken, which may indicate cloud/datacenter IP blocking
  — this needs verifying via the manual `workflow_dispatch` trigger once
  deployed, before assuming it works.
- Backtest results shown during development used **synthetic data**, not
  real market history. Before trusting the strategy, we should backtest
  against real historical data from Kraken/OANDA once deployed.
- No strategy is guaranteed to be profitable. Treat this as a tool for
  learning and disciplined execution, not a money-making guarantee.
