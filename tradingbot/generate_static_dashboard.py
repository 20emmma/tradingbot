"""
generate_static_dashboard.py

Renders the dashboard as a static HTML file instead of running a live
Flask server. Called at the end of every GitHub Actions run, right after
the bot's trading check -- the output (docs/index.html) gets committed
back to the repo alongside the state files, and GitHub Pages serves it
directly. No separate hosting service needed, no card, no sleep/cold-start.

The tradeoff vs. a live Flask dashboard: this only updates once per hour
(whenever the bot runs), not in real time. For a bot that only trades
once per hour anyway, that's not a meaningful loss.
"""

import json
import os
import glob
from jinja2 import Environment, FileSystemLoader

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "dashboard", "templates")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "docs")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "index.html")


def load_all_statuses():
    statuses = []
    for path in sorted(glob.glob(os.path.join(PROJECT_ROOT, "status_*.json"))):
        try:
            with open(path) as f:
                statuses.append(json.load(f))
        except (json.JSONDecodeError, FileNotFoundError):
            continue
    return statuses


def generate():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    template = env.get_template("dashboard.html")

    statuses = load_all_statuses()
    html = template.render(statuses=statuses)

    with open(OUTPUT_PATH, "w") as f:
        f.write(html)

    print(f"Static dashboard written to {OUTPUT_PATH} ({len(statuses)} market(s) included)")


if __name__ == "__main__":
    generate()
