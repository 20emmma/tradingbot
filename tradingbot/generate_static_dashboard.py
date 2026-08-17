"""
generate_static_dashboard.py

Renders the dashboard as a static HTML file. Called at the end of every
GitHub Actions run -- the output (docs/index.html) gets committed back to
the repo, and GitHub Pages serves it directly.
"""

import json
import os
import glob
from jinja2 import Environment, FileSystemLoader
from core.sparkline import build_sparkline_svg

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(PROJECT_ROOT, "dashboard", "templates")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "docs")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "index.html")


def load_all_statuses():
    statuses = []
    for path in sorted(glob.glob(os.path.join(PROJECT_ROOT, "status_*.json"))):
        try:
            with open(path) as f:
                status = json.load(f)
                prices = [p["price"] for p in status.get("price_history", [])]
                status["sparkline_svg"] = build_sparkline_svg(prices)
                statuses.append(status)
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
