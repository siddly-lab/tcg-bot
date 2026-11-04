"""Buy-timing numbers: where today's price sits against its own recent history, what you'd really
pay, and how sealed has done against plain investments."""
from __future__ import annotations

import csv
import datetime as dt
import io
import urllib.request

ZONE_LABELS = {
    "good_msrp": "At or below MSRP",
    "good_low": "Near its 90-day low",
    "normal": "In its normal range",
    "high": "Above its usual price",
    "new": "Not enough history yet",
}


def window(series: list, today: str, days: int = 90) -> list[float]:
    start = (dt.date.fromisoformat(today) - dt.timedelta(days=days)).isoformat()
    return [v for d, v in series if d >= start and v]


def stats(series: list, today: str, price: float | None, msrp: float | None, zones: dict) -> dict:
    """90-day low/high/average and a plain buy label."""
    w = window(series, today)
    out = {"low90": None, "high90": None, "avg90": None, "points90": len(w), "zone": "new"}
    if price is None:
        return out
    if w:
        out.update(low90=round(min(w), 2), high90=round(max(w), 2), avg90=round(sum(w) / len(w), 2))
        rng = out["high90"] - out["low90"]
        out["pos90"] = round((price - out["low90"]) / rng, 3) if rng > 0 else 0.5
        out["vs_low90"] = round(price / out["low90"] - 1, 4) if out["low90"] else None
    if msrp and price <= msrp:
        out["zone"] = "good_msrp"
    elif len(w) < zones["min_points"]:
        out["zone"] = "new"
    elif out["high90"] <= out["low90"] * (1 + zones["near_low_pct"]):
        out["zone"] = "normal"  # price has barely moved, so "near its low" would mean nothing
    elif price <= out["low90"] * (1 + zones["near_low_pct"]):
        out["zone"] = "good_low"
    elif price >= out["avg90"] * (1 + zones["above_usual_pct"]):
        out["zone"] = "high"
    else:
        out["zone"] = "normal"
    out["zone_label"] = ZONE_LABELS[out["zone"]]
    return out


def buy_cost(low: float | None, market: float | None, kind: str, buying: dict) -> float | None:
    """Cheapest listing plus shipping and sales tax."""
    base = low or market
    if not base:
        return None
    ship = buying["ship_single"] if kind == "card" else buying["ship_sealed"].get(kind, buying["ship_sealed"]["other"])
    return round(base * (1 + buying["sales_tax"]) + ship, 2)


# ---------------------------------------------------------------- benchmarks

def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "tcg-bot (+https://github.com/siddly-lab/tcg-bot)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode()


def fetch_benchmarks() -> dict:
    """S&P 500 (SPY closing prices) and 3-month Treasury bill rates. Empty if either source is down."""
    out = {}
    try:
        rows = list(csv.DictReader(io.StringIO(_get("https://stooq.com/q/d/l/?s=spy.us&i=d"))))
        out["spy"] = [(r["Date"], float(r["Close"])) for r in rows if r.get("Close") not in (None, "", "null")]
    except Exception as e:
        print("S&P 500 prices unavailable:", e)
    try:
        rows = list(csv.reader(io.StringIO(_get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DTB3"))))[1:]
        out["tbill"] = [(d, float(v)) for d, v in rows if v not in ("", ".")]
    except Exception as e:
        print("Treasury bill rates unavailable:", e)
    return out


def _on_or_after(series, day):
    for d, v in series:
        if d >= day:
            return v
    return None


def compare(release: str, today: str, msrp: float, value_now: float, bench: dict, tax: dict) -> dict | None:
    """What the same money would have done since release day, before and after federal tax."""
    days = (dt.date.fromisoformat(today) - dt.date.fromisoformat(release)).days
    if days < 90 or not msrp or not value_now:
        return None
    out = {"days": days, "sealed": round(value_now / msrp - 1, 4)}
    spy = bench.get("spy") or []
    if spy:
        a, b = _on_or_after(spy, release), spy[-1][1]
        if a:
            out["spy"] = round(b / a - 1, 4)
    tb = [v for d, v in (bench.get("tbill") or []) if release <= d <= today]
    if tb:
        out["tbill"] = round((1 + sum(tb) / len(tb) / 100) ** (days / 365) - 1, 4)
    out["after_tax"] = {
        "sealed": round(out["sealed"] * (1 - tax["collectibles_tax"]) if out["sealed"] > 0 else out["sealed"], 4),
        "spy": round(out["spy"] * (1 - tax["stock_tax"]) if out.get("spy", 0) > 0 else out.get("spy", 0), 4) if "spy" in out else None,
        "tbill": round(out["tbill"] * (1 - tax["interest_tax"]), 4) if "tbill" in out else None,
    }
    return out
