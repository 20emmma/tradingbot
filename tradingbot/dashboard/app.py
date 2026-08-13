"""
dashboard/app.py

A tiny, read-only web dashboard for the trading bot.

Two data source modes:
1. GITHUB_REPO env var set -> fetches status_*.json from the public repo's
   raw GitHub URL (this is how it runs on Render, reading state committed
   by the GitHub Actions workflow).
2. Not set -> reads local status_*.json files directly (useful for local
   testing, or if you're running the bot continuously on your own machine).

Run with:
    python3 dashboard/app.py
Then visit http://localhost:5000 (or your Render URL) in a browser.
"""

import json
import os
import glob
import requests
from flask import Flask, render_template

app = Flask(__name__)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GITHUB_REPO = os.environ.get("GITHUB_REPO", "")  # e.g. "yourusername/tradingbot"
GITHUB_BRANCH = os.environ.get("GITHUB_BRANCH", "main")
KNOWN_MARKETS = ["kraken", "oanda"]


def load_all_statuses():
    if GITHUB_REPO:
        return _load_from_github()
    return _load_from_local_disk()


def _load_from_github():
    statuses = []
    for market in KNOWN_MARKETS:
        url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/status_{market}.json"
        try:
            resp = requests.get(url, timeout=8)
            if resp.ok:
                statuses.append(resp.json())
        except (requests.RequestException, json.JSONDecodeError):
            continue  # that market's file doesn't exist yet or fetch failed -- skip it
    return statuses


def _load_from_local_disk():
    statuses = []
    for path in sorted(glob.glob(os.path.join(PROJECT_ROOT, "status_*.json"))):
        try:
            with open(path) as f:
                statuses.append(json.load(f))
        except (json.JSONDecodeError, FileNotFoundError):
            continue
    return statuses


@app.route("/")
def index():
    statuses = load_all_statuses()
    return render_template("dashboard.html", statuses=statuses)


if __name__ == "__main__":
    # Render sets $PORT automatically; DASHBOARD_PORT is used for local runs
    port = int(os.environ.get("PORT", os.environ.get("DASHBOARD_PORT", 5000)))
    app.run(host="0.0.0.0", port=port)
