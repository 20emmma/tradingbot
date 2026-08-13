# Deployment: keeping the bot (and dashboard) running

## 1. Install both systemd services

```bash
# Edit BOTH .service files first: replace YOUR_USERNAME with your actual
# server username, and confirm the paths match where you cloned the repo.

sudo cp deploy/tradingbot.service /etc/systemd/system/tradingbot.service
sudo cp deploy/tradingbot-dashboard.service /etc/systemd/system/tradingbot-dashboard.service
sudo systemctl daemon-reload
sudo systemctl enable tradingbot tradingbot-dashboard
sudo systemctl start tradingbot tradingbot-dashboard
```

They're separate services on purpose — restarting the dashboard (e.g.
after a UI tweak) never interrupts the actual trading bot, and vice versa.

## 2. Check it's running

```bash
sudo systemctl status tradingbot
sudo systemctl status tradingbot-dashboard
journalctl -u tradingbot -f          # live bot logs, Ctrl+C to stop watching
journalctl -u tradingbot-dashboard -f
```

Visit `http://<YOUR_SERVER_IP>:5000` to view the dashboard (see
`ORACLE_CLOUD_SETUP.md` step 6 for opening the firewall port first).

## 3. Common commands

```bash
sudo systemctl stop tradingbot
sudo systemctl restart tradingbot    # e.g. after pulling code changes or editing .env
sudo systemctl disable tradingbot    # stop it from auto-starting on reboot
# same commands work with tradingbot-dashboard
```

## Why this matters

Without this, the bot only runs as long as your SSH session / terminal
stays open. The moment you disconnect, it dies. `systemd` runs it as a
background service that:
- Survives you closing your laptop or losing SSH connection
- Automatically restarts if the bot crashes (e.g. a dropped network call it didn't recover from)
- Automatically starts again if the server itself reboots
- Gives you a real log history via `journalctl`, instead of losing output when the terminal closes
