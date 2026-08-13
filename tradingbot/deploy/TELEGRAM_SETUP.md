# Telegram Notifications Setup

## 1. Create your bot

1. Open Telegram, search for **@BotFather** (the official bot for making bots)
2. Send `/newbot`
3. Give it a name (e.g. "My Trading Bot Alerts") and a username (must end in `bot`, e.g. `my_tradingbot_alerts_bot`)
4. BotFather replies with a token that looks like `123456789:AAH...` — this is your `TELEGRAM_BOT_TOKEN`

## 2. Get your chat ID

1. Search for your new bot by its username and send it any message (e.g. "hi")
2. In your browser, visit (replace `<TOKEN>` with your real token):
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
3. You'll see JSON containing `"chat":{"id":123456789,...}` — that number is your `TELEGRAM_CHAT_ID`

## 3. Add both to your `.env`

```bash
TELEGRAM_BOT_TOKEN=123456789:AAH...
TELEGRAM_CHAT_ID=123456789
```

## 4. Restart the bot

```bash
sudo systemctl restart tradingbot
```

You should get a "Bot started" message within a few seconds. If you don't,
double check the token and chat ID were copied correctly (no extra spaces).

## What you'll be notified about

- Bot startup (mode, market, starting capital)
- Every position opened and closed (with price and PnL)
- Stop-losses triggering
- Daily loss limit being hit (trading paused for the day)
- Errors in the trading loop

Notifications are optional — if you leave these env vars blank, the bot
just skips them silently and logs everything normally instead.
