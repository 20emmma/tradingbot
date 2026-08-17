"""
core/sparkline.py

Generates a small inline SVG sparkline chart from a list of price points.
Deliberately dependency-free (no matplotlib, no JS charting library, no
CDN calls) so it works reliably in a static HTML file with zero external
requests -- important for a GitHub Pages dashboard that should render
correctly even if a CDN is slow/blocked/offline.
"""

from typing import List


def build_sparkline_svg(prices: List[float], width: int = 560, height: int = 90,
                         color: str = "#F0A83B", fill_color: str = "rgba(240,168,59,0.08)") -> str:
    """
    Returns an SVG <svg>...</svg> string showing a simple line chart of
    the given prices, oldest to newest, left to right.
    """
    if len(prices) < 2:
        return ""  # not enough data yet -- caller should show a placeholder instead

    padding = 4
    min_price = min(prices)
    max_price = max(prices)
    price_range = max_price - min_price or 1  # avoid divide-by-zero on flat data

    n = len(prices)
    step_x = (width - 2 * padding) / (n - 1)

    points = []
    for i, price in enumerate(prices):
        x = padding + i * step_x
        y = padding + (1 - (price - min_price) / price_range) * (height - 2 * padding)
        points.append((round(x, 1), round(y, 1)))

    line_points_str = " ".join(f"{x},{y}" for x, y in points)
    area_points_str = line_points_str + f" {points[-1][0]},{height} {points[0][0]},{height}"

    latest_up = prices[-1] >= prices[0]
    line_color = "#5FD97A" if latest_up else "#F0605A"
    area_fill = "rgba(95,217,122,0.08)" if latest_up else "rgba(240,96,90,0.08)"

    svg = f'''<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" preserveAspectRatio="none" style="display:block;">
  <polygon points="{area_points_str}" fill="{area_fill}" />
  <polyline points="{line_points_str}" fill="none" stroke="{line_color}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" />
</svg>'''
    return svg
