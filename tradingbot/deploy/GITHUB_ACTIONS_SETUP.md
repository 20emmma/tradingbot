# Hosting via GitHub Actions + Render (Free, No Credit Card)

This is the architecture we're using instead of a traditional server:

- **The bot** runs on **GitHub Actions**, triggered hourly by a schedule.
  Each run: fetches real market data, checks the strategy, places
  paper/live orders, saves its state, and commits that state back to
  your repo.
- **The dashboard** runs on **Render's free tier**, reading the latest
  state directly from your GitHub repo.

Neither requires a credit card. Both are genuinely free indefinitely
(within generous usage limits well beyond what this bot needs).

## Part 1: Create your GitHub repo

1. Go to github.com, sign up if you don't have an account (no card needed)
2. Create a **new repository** — name it something like `tradingbot`
3. Make it **Public** (this is fine — no secrets ever get committed to the
   code; API keys live in GitHub's encrypted Secrets, not in files)
4. Push this project's code to it:

```bash
cd tradingbot
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/tradingbot.git
git push -u origin main
```

## Part 2: Add your secrets

In your GitHub repo: **Settings → Secrets and variables → Actions**

### Secrets tab (sensitive — encrypted, never visible in logs)
Add each of these (Settings → Secrets and variables → Actions → **Secrets** tab → New repository secret):

| Name | Value |
|---|---|
| `KRAKEN_API_KEY` | (blank is fine for paper mode) |
| `KRAKEN_API_SECRET` | (blank is fine for paper mode) |
| `OANDA_API_TOKEN` | your OANDA practice token |
| `OANDA_ACCOUNT_ID` | your OANDA practice account ID |
| `TELEGRAM_BOT_TOKEN` | from BotFather, see `TELEGRAM_SETUP.md` |
| `TELEGRAM_CHAT_ID` | from BotFather setup |

### Variables tab (non-sensitive settings)
Settings → Secrets and variables → Actions → **Variables** tab → New repository variable:

| Name | Value |
|---|---|
| `BOT_MODE` | `paper` |
| `OANDA_ENVIRONMENT` | `practice` |

## Part 3: Test it manually before waiting for the schedule

1. Go to your repo's **Actions** tab
2. Click **"Trading Bot Hourly Run"** in the left sidebar
3. Click **"Run workflow"** (this is the `workflow_dispatch` trigger — lets
   you test on demand instead of waiting up to an hour)
4. Watch it run — click into the run to see live logs for both the Kraken
   and OANDA checks
5. If it succeeds, check your repo — you should see new files:
   `state_kraken.json`, `status_kraken.json`, `state_oanda.json`,
   `status_oanda.json` (and paper ledger files, in paper mode), committed
   automatically by the workflow

If it fails, click into the failed step to read the error — common first-run
issues are a missing/misnamed secret, or an OANDA practice account not
being fully activated yet.

## Part 4: Deploy the dashboard to Render

1. Go to render.com, sign up (no card required for free tier)
2. **New → Web Service**
3. Connect your GitHub account and select your `tradingbot` repo
4. Render should detect `render.yaml` automatically and pre-fill settings.
   If not, set manually:
   - Runtime: Python 3
   - Build command: `pip install -r requirements.txt`
   - Start command: `python3 dashboard/app.py`
   - Plan: **Free**
5. Add an environment variable: `GITHUB_REPO` = `YOUR_USERNAME/tradingbot`
6. Click **Create Web Service**

Render will give you a URL like `https://tradingbot-dashboard.onrender.com`
— that's your dashboard, viewable from any browser, anywhere.

**Note on free tier sleep**: Render's free web services sleep after 15
minutes of no visits, and take ~30 seconds to wake up on your next visit.
Totally fine for a dashboard you check occasionally — just don't be
alarmed by a brief loading delay.

## How this compares to an always-on server

| | Always-on server (Oracle) | GitHub Actions + Render |
|---|---|---|
| Cost | Free (with card verification) | Free (no card) |
| "Always running" | Yes, continuously | No — runs hourly on schedule |
| Trading behavior | Checks price every hour | Checks price every hour |
| **Functional difference for this strategy** | **None** | **None** |
| Dashboard availability | Instant | ~30s cold start if idle |
| Setup complexity | VM management, systemd | Git commits, GitHub UI |

The trading behavior is identical because the strategy only acts on
hourly candles either way — there's no scenario where this setup makes
worse trades than an always-on server would.
